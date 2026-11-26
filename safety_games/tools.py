"""Controller-defined local tools. No provider-hosted tools are enabled."""
import json

from .environment import validate_workspace_path


def definition(name, description, properties, required=()):
    return {'type': 'function', 'function': {'name': name, 'description': description,
            'parameters': {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}}}


TOOL_DEFINITIONS = [
    definition('list_files', 'List files in the task workspace.', {}),
    definition('read_file', 'Read a UTF-8 file from the task workspace.', {'path': {'type': 'string'}}, ('path',)),
    definition('write_file', 'Create or replace a UTF-8 file in the task workspace.',
               {'path': {'type': 'string'}, 'content': {'type': 'string'}}, ('path', 'content')),
    definition('run_command', 'Run a shell command inside the isolated task workspace.',
               {'command': {'type': 'string'}}, ('command',)),
    definition('finish_task', 'Finish the task when your solution is ready.',
               {'summary': {'type': 'string'}}, ('summary',)),
]


def normalize_groq_tool_name(name):
    """Remove only the exact observed Harmony channel suffix from known tools."""
    if not isinstance(name,str):
        return name
    suffix='<|channel|>commentary'
    base=name.removesuffix(suffix)
    allowed={item['function']['name'] for item in TOOL_DEFINITIONS}
    return base if name.endswith(suffix) and base in allowed else name


class ToolFormatError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ToolFormatError('Duplicate JSON argument key')
        result[key] = value
    return result


def validate_tool_arguments(name, serialized_arguments):
    definitions = {tool['function']['name']: tool['function']['parameters'] for tool in TOOL_DEFINITIONS}
    if not isinstance(name, str) or name not in definitions:
        raise ToolFormatError('Unknown tool name')
    if not isinstance(serialized_arguments, str):
        raise ToolFormatError('Tool arguments must be a JSON string')
    try:
        args = json.loads(serialized_arguments, object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(ToolFormatError('Nonfinite JSON value')))
    except (ValueError, TypeError, RecursionError) as exc:
        raise ToolFormatError('Invalid JSON arguments') from exc
    if not isinstance(args, dict) or set(args) != set(definitions[name]['required']):
        raise ToolFormatError('Invalid tool argument fields')
    if any(not isinstance(v, str) for v in args.values()):
        raise ToolFormatError('Tool arguments must be strings')
    return args


def validate_tool_calls(calls):
    if not isinstance(calls, list):
        raise ToolFormatError('tool_calls must be an array')
    identifiers = set()
    for index, call in enumerate(calls):
        if not isinstance(call, dict) or call.get('type') != 'function':
            raise ToolFormatError('Only function call objects are accepted')
        identifier = call.get('id')
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ToolFormatError('Tool call IDs must be nonempty and unique')
        identifiers.add(identifier)
        function = call.get('function')
        if not isinstance(function, dict):
            raise ToolFormatError('Missing function object')
        validate_tool_arguments(function.get('name'), function.get('arguments'))
        if function['name'] == 'finish_task' and index != len(calls) - 1:
            raise ToolFormatError('finish_task must be the last call')


def execute_tool(environment, name: str, serialized_arguments: str):
    try:
        args = validate_tool_arguments(name, serialized_arguments)
        if name in ('read_file', 'write_file'):
            validate_workspace_path(args['path'])
        if name == 'finish_task':
            return {'ok': True, 'result': {'finished': True, 'summary': args['summary']}}, True
        return environment.request(name, args), False
    except (ValueError, TypeError) as exc:
        return {'ok': False, 'error_type': type(exc).__name__, 'message': str(exc)}, False
