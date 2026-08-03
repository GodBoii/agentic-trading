# python-backend/test_r2.py

import os
from dotenv import load_dotenv
from r2_client import R2Client

# Load environment variables
load_dotenv()

def test_r2_setup():
    """Test R2 configuration and connectivity."""
    print("=" * 50)
    print("R2 CONFIGURATION TEST")
    print("=" * 50)
    
    # Check environment variables
    print("\n1. Checking environment variables...")
    required_vars = ['R2_ENDPOINT', 'R2_BUCKET', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY']
    for var in required_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            if 'KEY' in var or 'SECRET' in var:
                display = value[:8] + '...' + value[-4:]
            else:
                display = value
            print(f"   ✓ {var}: {display}")
        else:
            print(f"   ✗ {var}: NOT SET")
            return False
    
    # Initialize client
    print("\n2. Initializing R2 client...")
    try:
        client = R2Client()
        print("   ✓ Client initialized")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return False
    
    # Test connection
    print("\n3. Testing connection to R2...")
    if client.test_connection():
        print("   ✓ Connection successful")
    else:
        print("   ✗ Connection failed")
        return False
    
    # Test upload
    print("\n4. Testing file upload...")
    test_key = "test/hello.txt"
    test_content = "Hello from Aetheria AI! This is a test file."
    result = client.upload_text(test_key, test_content)
    if result['success']:
        print(f"   ✓ Upload successful")
        print(f"     - Size: {result['size']} bytes")
        print(f"     - Checksum: {result['checksum'][:16]}...")
    else:
        print(f"   ✗ Upload failed: {result.get('error')}")
        return False
    
    # Test presigned URL generation
    print("\n5. Testing presigned URL generation...")
    url = client.generate_presigned_get_url(test_key, expiry=300)
    if url:
        print(f"   ✓ Presigned URL generated")
        print(f"     - URL: {url[:60]}...")
    else:
        print("   ✗ Failed to generate URL")
        return False
    
    # Cleanup test file
    print("\n6. Cleaning up test file...")
    if client.delete_object(test_key):
        print("   ✓ Cleanup successful")
    else:
        print("   ✗ Cleanup failed (not critical)")
    
    print("\n" + "=" * 50)
    print("✓ ALL TESTS PASSED!")
    print("=" * 50)
    print("\nYour R2 storage is ready to use!")
    print("You can now proceed with implementing sandbox persistence.")
    return True

if __name__ == "__main__":
    success = test_r2_setup()
    exit(0 if success else 1)
