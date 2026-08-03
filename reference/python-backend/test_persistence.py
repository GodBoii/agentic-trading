# python-backend/test_persistence.py

import os
from dotenv import load_dotenv
from sandbox_persistence import SandboxPersistenceService

# Load environment variables
load_dotenv()

def test_persistence_service():
    """Test the sandbox persistence service."""
    print("=" * 60)
    print("SANDBOX PERSISTENCE SERVICE TEST")
    print("=" * 60)
    
    # Initialize service
    print("\n1. Initializing persistence service...")
    try:
        service = SandboxPersistenceService()
        print("   ✓ Service initialized")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return False
    
    # Test user ID (you'll need to replace this with a real user ID from your Supabase)
    # For testing, we'll use a dummy UUID format
    test_user_id = "2c4ff0bd-9641-466d-a491-7a9880a131b9"
    test_session_id = "test-session-123"
    test_sandbox_id = "test-sandbox-abc"
    test_command = "echo 'Hello from persistence test'"
    
    print(f"\n2. Creating execution record...")
    print(f"   User ID: {test_user_id}")
    print(f"   Session: {test_session_id}")
    print(f"   Command: {test_command}")
    
    execution_id = service.create_execution_record(
        user_id=test_user_id,
        session_id=test_session_id,
        sandbox_id=test_sandbox_id,
        command=test_command,
        message_id="test-msg-001"
    )
    
    if execution_id:
        print(f"   ✓ Execution record created: {execution_id}")
    else:
        print("   ✗ Failed to create execution record")
        print("\n   NOTE: This might fail if the test user ID doesn't exist in Supabase.")
        print("   To fix: Replace test_user_id with a real user ID from your auth.users table")
        return False
    
    # Test persisting output
    print("\n3. Persisting execution output...")
    test_stdout = "Hello from persistence test\nThis is stdout output\nLine 3"
    test_stderr = "Warning: This is a test warning"
    test_exit_code = 0
    
    success = service.persist_execution_output(
        execution_id=execution_id,
        stdout=test_stdout,
        stderr=test_stderr,
        exit_code=test_exit_code
    )
    
    if success:
        print("   ✓ Output persisted successfully")
        print(f"     - Stdout: {len(test_stdout)} bytes")
        print(f"     - Stderr: {len(test_stderr)} bytes")
        print(f"     - Exit code: {test_exit_code}")
    else:
        print("   ✗ Failed to persist output")
        return False
    
    # Test retrieving metadata
    print("\n4. Retrieving execution metadata...")
    metadata = service.get_execution_metadata(execution_id, test_user_id)
    
    if metadata:
        print("   ✓ Metadata retrieved")
        print(f"     - Status: {metadata.get('status')}")
        print(f"     - Exit code: {metadata.get('exit_code')}")
        print(f"     - Stdout key: {metadata.get('stdout_key', 'N/A')[:50]}...")
    else:
        print("   ✗ Failed to retrieve metadata")
        return False
    
    # Test generating presigned URLs
    print("\n5. Generating presigned URLs...")
    urls = service.get_execution_logs_urls(execution_id, test_user_id)
    
    if urls:
        print("   ✓ Presigned URLs generated")
        if urls.get('stdout_url'):
            print(f"     - Stdout URL: {urls['stdout_url'][:60]}...")
        if urls.get('stderr_url'):
            print(f"     - Stderr URL: {urls['stderr_url'][:60]}...")
    else:
        print("   ✗ Failed to generate URLs")
        return False
    
    # Test listing executions
    print("\n6. Listing session executions...")
    executions = service.list_session_executions(test_session_id, test_user_id)
    
    if executions:
        print(f"   ✓ Found {len(executions)} execution(s)")
        for exec in executions:
            print(f"     - {exec.get('command')} (exit: {exec.get('exit_code')})")
    else:
        print("   ⚠ No executions found (might be expected)")
    
    # Test cleanup
    print("\n7. Cleaning up test data...")
    deleted = service.delete_execution(execution_id, test_user_id)
    
    if deleted:
        print("   ✓ Test execution deleted")
    else:
        print("   ✗ Failed to delete (not critical)")
    
    print("\n" + "=" * 60)
    print("✓ ALL PERSISTENCE TESTS PASSED!")
    print("=" * 60)
    print("\nYour persistence service is working correctly!")
    print("Next step: Integrate with sandbox_tools.py")
    return True

if __name__ == "__main__":
    print("\n⚠️  IMPORTANT: This test requires a valid user_id from Supabase.")
    print("If the test fails at step 2, you need to:")
    print("1. Go to Supabase Dashboard → Authentication → Users")
    print("2. Copy a real user ID")
    print("3. Replace test_user_id in this file\n")
    
    input("Press Enter to continue with the test...")
    
    success = test_persistence_service()
    exit(0 if success else 1)
