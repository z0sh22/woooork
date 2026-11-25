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


def execute_tool(environment, name: str, serialized_arguments: str):
    definitions = {tool['function']['name']: tool['function']['parameters'] for tool in TOOL_DEFINITIONS}
    if name not in definitions:
        return {'ok': False, 'error_type': 'UnknownTool'}, False
    try:
        args = json.loads(serialized_arguments)
        schema = definitions[name]
        if not isinstance(args, dict) or set(args) != set(schema['required']):
            raise ValueError('Invalid tool argument fields')
        if any(not isinstance(v, str) for v in args.values()):
            raise ValueError('Tool arguments must be strings')
        if name in ('read_file', 'write_file'):
            validate_workspace_path(args['path'])
        if name == 'finish_task':
            return {'ok': True, 'result': {'finished': True, 'summary': args['summary']}}, True
        return environment.request(name, args), False
    except (ValueError, TypeError) as exc:
        return {'ok': False, 'error_type': type(exc).__name__, 'message': str(exc)}, False
