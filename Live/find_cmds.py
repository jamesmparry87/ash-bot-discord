import os, re

def find_commands():
    defined_cmds = set()
    used_cmds = set()

    # Find defined commands using regex
    cmd_pattern = re.compile(r'@commands\.command\([^)]*name=[\'\"]([a-z_]+)[\'\"]')
    aliases_pattern = re.compile(r'@commands\.command\([^)]*aliases=\[([^\]]+)\]')
    
    for root, _, files in os.walk('bot/commands'):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Find names
                for match in cmd_pattern.finditer(content):
                    defined_cmds.add(match.group(1).lower())
                    
                # Find aliases
                for match in aliases_pattern.finditer(content):
                    aliases_str = match.group(1)
                    # parse 'alias1', "alias2"
                    aliases = re.findall(r'[\'\"]([a-z_]+)[\'\"]', aliases_str)
                    for alias in aliases:
                        defined_cmds.add(alias.lower())

    # Find used commands in strings anywhere
    string_pattern = re.compile(r'![a-z_]+')
    for root, _, files in os.walk('.'):
        if '.git' in root or '.pytest' in root or '__pycache__' in root or 'venv' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                matches = string_pattern.findall(content.lower())
                for match in matches:
                    used_cmds.add(match[1:]) # remove !

    print('Missing commands (used but not defined):')
    missing = used_cmds - defined_cmds
    for m in sorted(list(missing)):
        print(f' - !{m}')
    
    print('\nDefined commands:')
    for m in sorted(list(defined_cmds)):
        print(f' - !{m}')

find_commands()
