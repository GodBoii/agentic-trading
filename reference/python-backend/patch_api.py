import re

def patch_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 1. Update imports
    for i, line in enumerate(lines):
        if line.startswith("from extensions import socketio"):
            lines[i] = "from extensions import socketio, limiter\n"
            break

    # 2. Add decorators to routes
    replacements = {
        "def conversation_run_status": "@limiter.limit('120 per minute')",
        "def conversation_run_result": "@limiter.limit('120 per minute')",
        "def subscription_status": "@limiter.limit('100 per minute')",
        "def usage_daily_for_user": "@limiter.limit('60 per minute')",
        "def usage_daily_admin": "@limiter.limit('60 per minute')",
        "def subscription_create": "@limiter.limit('10 per minute')",
        "def subscription_verify": "@limiter.limit('10 per minute')",
        "def razorpay_webhook": "@limiter.limit('100 per minute')",
        "def get_integrations_status": "@limiter.limit('60 per minute')",
        "def disconnect_integration": "@limiter.limit('20 per minute')",
        "def list_memories": "@limiter.limit('100 per minute')",
        "def create_memory": "@limiter.limit('100 per minute')",
        "def memory_by_id": "@limiter.limit('100 per minute')",
        "def composio_status": "@limiter.limit('30 per minute')",
        "def composio_disconnect": "@limiter.limit('10 per minute')",
        "def composio_connect_url": "@limiter.limit('10 per minute')",
        "def composio_tools": "@limiter.limit('30 per minute')",
        "def generate_upload_url": "@limiter.limit('20 per minute')",
    }

    new_lines = []
    for line in lines:
        for target, limit_dec in replacements.items():
            if line.strip().startswith(target) and "@limiter.limit" not in "".join(new_lines[-2:]):
                indent = line[:len(line) - len(line.lstrip())]
                new_lines.append(f"{indent}{limit_dec}\n")
        new_lines.append(line)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    print("Patched successfully")

if __name__ == "__main__":
    patch_file("api.py")
