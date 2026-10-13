import os
import boto3
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

def test_s3_connection():
    print("Testing AWS S3 Connectivity...")
    
    # Retrieve credentials from environment
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION")
    bucket_name = os.getenv("AWS_S3_BUCKET")
    
    if not all([aws_access_key, aws_secret_key, bucket_name]):
        print("❌ Missing AWS credentials in .env file.")
        return

    try:
        # Initialize S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region
        )
        
        print(f"✅ Successfully initialized S3 client for region {aws_region}.")
        
        # 1. Test creating and uploading a small file
        test_file_name = "test_upload.txt"
        test_content = "This is a test file to verify S3 connectivity for the PQC project."
        
        print(f"Attempting to upload '{test_file_name}' to bucket '{bucket_name}'...")
        s3_client.put_object(
            Bucket=bucket_name,
            Key=test_file_name,
            Body=test_content
        )
        print(f"✅ Successfully uploaded '{test_file_name}'.")
        
        # 2. Test reading the file back
        print("Attempting to read the file back...")
        response = s3_client.get_object(Bucket=bucket_name, Key=test_file_name)
        data = response['Body'].read().decode('utf-8')
        print(f"✅ Successfully read file content: '{data}'")
        
        # 3. Test listing objects in the bucket
        print("Attempting to list objects in the bucket...")
        response = s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=5)
        
        if 'Contents' in response:
            print(f"✅ Successfully listed objects. Found {len(response['Contents'])} objects (showing up to 5):")
            for obj in response['Contents']:
                print(f"  - {obj['Key']} ({obj['Size']} bytes)")
        else:
            print("✅ Successfully accessed bucket, but it is empty (other than our test file, which might not be listed if pagination delayed).")
            
        print("\n🎉 AWS S3 Cloud Integration is FULLY FUNCTIONAL! 🎉")
        
    except Exception as e:
        print(f"\n❌ S3 Connection Test Failed: {str(e)}")

if __name__ == "__main__":
    test_s3_connection()
