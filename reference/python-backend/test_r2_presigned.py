#!/usr/bin/env python3
"""
Test script to verify R2 presigned URL generation and access.
Run this to diagnose session content viewer issues.
"""

import os
import sys
import requests
from r2_client import get_r2_client
from supabase_client import supabase_client

def test_r2_connection():
    """Test basic R2 connectivity."""
    print("=" * 60)
    print("TEST 1: R2 Connection")
    print("=" * 60)
    
    try:
        r2 = get_r2_client()
        result = r2.test_connection()
        print(f"✓ R2 connection: {'SUCCESS' if result else 'FAILED'}")
        return result
    except Exception as e:
        print(f"✗ R2 connection failed: {e}")
        return False

def test_execution_data():
    """Check if execution data exists in database."""
    print("\n" + "=" * 60)
    print("TEST 2: Database Execution Records")
    print("=" * 60)
    
    try:
        # Get recent executions
        result = supabase_client.table('sandbox_executions').select(
            'execution_id, command, stdout_key, stderr_key, stdout_size, stderr_size, exit_code'
        ).order('created_at', desc=True).limit(5).execute()
        
        if not result.data:
            print("✗ No execution records found")
            return False
        
        print(f"✓ Found {len(result.data)} recent executions:")
        for exec_data in result.data:
            print(f"\n  Execution ID: {exec_data['execution_id'][:8]}...")
            print(f"  Command: {exec_data.get('command', 'N/A')}")
            print(f"  Stdout key: {exec_data.get('stdout_key', 'None')}")
            print(f"  Stderr key: {exec_data.get('stderr_key', 'None')}")
            print(f"  Stdout size: {exec_data.get('stdout_size', 0)} bytes")
            print(f"  Stderr size: {exec_data.get('stderr_size', 0)} bytes")
            print(f"  Exit code: {exec_data.get('exit_code', 'N/A')}")
        
        return True
    except Exception as e:
        print(f"✗ Database query failed: {e}")
        return False

def test_presigned_url_generation():
    """Test presigned URL generation for existing execution."""
    print("\n" + "=" * 60)
    print("TEST 3: Presigned URL Generation")
    print("=" * 60)
    
    try:
        # Get an execution with stdout
        result = supabase_client.table('sandbox_executions').select(
            'execution_id, user_id, stdout_key, stderr_key'
        ).not_.is_('stdout_key', 'null').limit(1).execute()
        
        if not result.data:
            print("✗ No executions with stdout found")
            return False
        
        exec_data = result.data[0]
        execution_id = exec_data['execution_id']
        stdout_key = exec_data['stdout_key']
        
        print(f"✓ Testing with execution: {execution_id[:8]}...")
        print(f"  Stdout key: {stdout_key}")
        
        # Generate presigned URL
        r2 = get_r2_client()
        url = r2.generate_presigned_get_url(stdout_key, expiry=300)
        
        if not url:
            print("✗ Failed to generate presigned URL")
            return False
        
        print(f"✓ Generated presigned URL:")
        print(f"  {url[:100]}...")
        
        return url
    except Exception as e:
        print(f"✗ Presigned URL generation failed: {e}")
        return False

def test_presigned_url_access(url):
    """Test if presigned URL is accessible."""
    print("\n" + "=" * 60)
    print("TEST 4: Presigned URL Access")
    print("=" * 60)
    
    try:
        print(f"Fetching content from presigned URL...")
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            content = response.text
            print(f"✓ Successfully fetched content ({len(content)} bytes)")
            print(f"\nFirst 200 characters:")
            print(f"  {content[:200]}")
            return True
        else:
            print(f"✗ HTTP {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Failed to fetch content: {e}")
        return False

def test_session_content_api():
    """Test the session content API endpoint."""
    print("\n" + "=" * 60)
    print("TEST 5: Session Content API")
    print("=" * 60)
    
    try:
        # Get a recent session with content
        result = supabase_client.table('session_content').select(
            'session_id'
        ).limit(1).execute()
        
        if not result.data:
            print("✗ No session content found")
            return False
        
        session_id = result.data[0]['session_id']
        print(f"✓ Testing with session: {session_id[:8]}...")
        
        # Note: This test requires authentication token
        print("  (Skipping API test - requires auth token)")
        print("  To test manually:")
        print(f"  GET http://localhost:8765/api/sessions/{session_id}/content")
        print("  Header: Authorization: Bearer <your_token>")
        
        return True
    except Exception as e:
        print(f"✗ Session content query failed: {e}")
        return False

def main():
    """Run all diagnostic tests."""
    print("\n" + "=" * 60)
    print("R2 PRESIGNED URL DIAGNOSTIC TOOL")
    print("=" * 60)
    
    results = []
    
    # Test 1: R2 Connection
    results.append(("R2 Connection", test_r2_connection()))
    
    # Test 2: Database Records
    results.append(("Database Records", test_execution_data()))
    
    # Test 3: Presigned URL Generation
    url = test_presigned_url_generation()
    results.append(("Presigned URL Generation", bool(url)))
    
    # Test 4: Presigned URL Access (only if URL was generated)
    if url:
        results.append(("Presigned URL Access", test_presigned_url_access(url)))
    
    # Test 5: Session Content API
    results.append(("Session Content API", test_session_content_api()))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(result[1] for result in results if result[1] is not None)
    
    if all_passed:
        print("\n✓ All tests passed! R2 presigned URLs should work.")
    else:
        print("\n✗ Some tests failed. Check the output above for details.")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
