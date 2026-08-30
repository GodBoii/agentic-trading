import re

with open('python-backend/pipeline/stages/intra_finder.py', 'r') as f:
    lines = f.readlines()

def get_indent(line):
    return len(line) - len(line.lstrip())

def delete_method(method_name, lines):
    new_lines = []
    skip = False
    base_indent = -1
    for line in lines:
        if re.match(r'^\s*def ' + method_name + r'\(', line):
            skip = True
            base_indent = get_indent(line)
            continue
            
        if skip:
            if line.strip() == '' or get_indent(line) > base_indent:
                continue
            if line.lstrip().startswith(')') or line.lstrip().startswith('->'):
                continue
            if get_indent(line) == base_indent and line.lstrip().startswith('def '):
                skip = False
            elif get_indent(line) <= base_indent and line.strip() != '':
                skip = False
                
        if not skip:
            new_lines.append(line)
    return new_lines

methods_to_delete = [
    '_setup_candidate', '_score', '_hard_gates', '_indicator_direction',
    '_indicator_attention_score', '_queue_indicator_evidence',
    '_indicator_safety_gates', '_weak_indicator_evidence_only',
    '_reschedule_readiness_evaluation', '_create_indicator_event',
    '_flush_due_indicator_events', '_event_key', '_active_setup_key',
    '_update_active_setup_invalidations', '_create_event', '_rebuild_indicator_deadlines'
]

for method in methods_to_delete:
    lines = delete_method(method, lines)

with open('python-backend/pipeline/stages/intra_finder.py', 'w') as f:
    f.writelines(lines)

print("Deleted legacy methods.")
