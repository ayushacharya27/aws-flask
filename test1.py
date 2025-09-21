import os
import json
import uuid
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import boto3
from botocore.exceptions import ClientError
import mimetypes

app = Flask(__name__)
CORS(app)


# Initialize S3 client with explicit credentials
s3 = boto3.client("s3")
BUCKET_NAME = "aws23bps"

def generate_unique_filename(user_id, original_filename):
    """Generate a unique filename with user_id and timestamp"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_extension = os.path.splitext(original_filename)[1]
    #unique_id = str(uuid.uuid4())[:8]
    #return f"{user_id}_{timestamp}_{unique_id}{file_extension}"
    return f"{user_id}_{timestamp}{file_extension}"

def determine_media_type(filename):
    """Determine if file is image or video based on extension"""
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        if mime_type.startswith('image/'):
            return 'image'
        elif mime_type.startswith('video/'):
            return 'video'
    return 'unknown'

def upload_metadata_to_s3(filename, metadata, username):
    """Upload metadata as JSON to S3"""
    metadata_key = f"metadata/{username}/{filename}.json"
    try:
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=metadata_key,
            Body=json.dumps(metadata),
            ContentType='application/json'
        )
        return True
    except Exception as e:
        print(f"Failed to upload metadata: {e}")
        return False

def get_presigned_url(object_key, expiration=3600):
    """Generate a presigned URL for S3 object"""
    try:
        response = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET_NAME, 'Key': object_key},
            ExpiresIn=expiration
        )
        return response
    except ClientError as e:
        print(f"Error generating presigned URL: {e}")
        return None

@app.route('/upload', methods=['POST', 'OPTIONS'])
def upload_file():
    """Handle file upload with caption and user info"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        # Get form data
        if 'files' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['files']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        caption = request.form.get('caption', '')
        username = request.form.get('username', 'anonymous')
        
        # Debug: Log the username being received
        print(f"DEBUG: Received username from frontend: '{username}'")
        
        # Generate unique filename
        unique_filename = generate_unique_filename(username, file.filename)
        media_key = f"media/{username}/{unique_filename}"
        
        # Determine media type
        media_type = determine_media_type(file.filename)
        
        # Create metadata
        metadata = {
            'filename': unique_filename,
            'original_filename': file.filename,
            'username': username,
            'caption': caption,
            'media_type': media_type,
            'upload_timestamp': datetime.now().isoformat(),
            'file_size': len(file.read()),
            's3_key': media_key
        }
        
        # Reset file pointer
        file.seek(0)
        
        # Upload file to S3
        try:
            s3.upload_fileobj(
                file,
                BUCKET_NAME,
                media_key,
                ExtraArgs={'ContentType': file.content_type} if file.content_type else None
            )
        except Exception as e:
            return jsonify({'error': f'Failed to upload file to S3: {str(e)}'}), 500
        
        # Upload metadata to S3
        if not upload_metadata_to_s3(unique_filename, metadata, username):
            return jsonify({'error': 'File uploaded but failed to save metadata'}), 500
        
        return jsonify({
            'message': 'File uploaded successfully',
            'filename': unique_filename,
            'media_type': media_type,
            'metadata': metadata,
            'username' : username
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/media', methods=['GET'])
def get_media():
    """Get media from other users (excluding current user)"""
    try:
        current_user = request.args.get('current_user', '')
        
        # List all metadata files from S3
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=f'metadata/')
        
        if 'Contents' not in response:
            return jsonify({f'media/{username}': []}), 200
        
        media_list = []
        
        for obj in response['Contents']:
            metadata_key = obj['Key']
            
            # Skip if not a JSON file
            if not metadata_key.endswith('.json'):
                continue
            
            try:
                # Get metadata from S3
                metadata_response = s3.get_object(Bucket=BUCKET_NAME, Key=metadata_key)
                metadata = json.loads(metadata_response['Body'].read())
                
                # Skip if it's the current user's media
                if metadata.get('username') == current_user:
                    continue
                
                # Generate presigned URL for the media file
                media_url = get_presigned_url(metadata['s3_key'])
                if media_url:
                    media_item = {
                        'id': metadata.get('filename', '').replace('.', '_'),
                        'type': metadata.get('media_type', 'unknown'),
                        'username': metadata.get('username', 'unknown'),
                        'caption': metadata.get('caption', ''),
                        'timestamp': metadata.get('upload_timestamp', ''),
                        'url': media_url,
                        'original_filename': metadata.get('original_filename', ''),
                        'file_size': metadata.get('file_size', 0)
                    }
                    
                    # Add type-specific fields
                    if media_item['type'] == 'video':
                        media_item['videoUrl'] = media_url
                        # You can add thumbnail generation logic here
                        media_item['thumbnail'] = media_url  # For now, use same URL
                    elif media_item['type'] == 'image':
                        media_item['imageUrl'] = media_url
                    
                    media_list.append(media_item)
                    
            except Exception as e:
                print(f"Error processing metadata {metadata_key}: {e}")
                continue
        
        # Sort by timestamp (newest first)
        media_list.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({'media': media_list}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to retrieve media: {str(e)}'}), 500

@app.route('/user-media', methods=['GET'])
def get_user_media():
    """Get media for a specific user"""
    try:
        username = request.args.get('username', '')
        if not username:
            return jsonify({'error': 'Username required'}), 400
        
        # List all metadata files from S3
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix='metadata/')
        
        if 'Contents' not in response:
            return jsonify({'media': []}), 200
        
        user_media = []
        
        for obj in response['Contents']:
            metadata_key = obj['Key']
            
            if not metadata_key.endswith('.json'):
                continue
            
            try:
                # Get metadata from S3
                metadata_response = s3.get_object(Bucket=BUCKET_NAME, Key=metadata_key)
                metadata = json.loads(metadata_response['Body'].read())
                
                # Only include this user's media
                if metadata.get('username') == username:
                    media_url = get_presigned_url(metadata['s3_key'])
                    if media_url:
                        media_item = {
                            'id': metadata.get('filename', '').replace('.', '_'),
                            'type': metadata.get('media_type', 'unknown'),
                            'username': metadata.get('username', 'unknown'),
                            'caption': metadata.get('caption', ''),
                            'timestamp': metadata.get('upload_timestamp', ''),
                            'url': media_url,
                            'original_filename': metadata.get('original_filename', ''),
                            'file_size': metadata.get('file_size', 0)
                        }
                        user_media.append(media_item)
                        
            except Exception as e:
                print(f"Error processing metadata {metadata_key}: {e}")
                continue
        
        # Sort by timestamp (newest first)
        user_media.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify({'media': user_media}), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to retrieve user media: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'bucket': BUCKET_NAME
    }), 200

@app.route('/delete-media', methods=['DELETE'])
def delete_media():
    """Delete a media file and its metadata"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        username = data.get('username')
        
        if not filename or not username:
            return jsonify({'error': 'Filename and username required'}), 400
        
        # Verify ownership by checking metadata
        metadata_key = f"metadata/{filename}.json"
        try:
            metadata_response = s3.get_object(Bucket=BUCKET_NAME, Key=metadata_key)
            metadata = json.loads(metadata_response['Body'].read())
            
            if metadata.get('username') != username:
                return jsonify({'error': 'Unauthorized to delete this media'}), 403
                
        except ClientError:
            return jsonify({'error': 'Media not found'}), 404
        
        # Delete media file and metadata
        media_key = f"media/{filename}"
        
        try:
            s3.delete_object(Bucket=BUCKET_NAME, Key=media_key)
            s3.delete_object(Bucket=BUCKET_NAME, Key=metadata_key)
            
            return jsonify({'message': 'Media deleted successfully'}), 200
            
        except Exception as e:
            return jsonify({'error': f'Failed to delete media: {str(e)}'}), 500
        
    except Exception as e:
        return jsonify({'error': f'Delete operation failed: {str(e)}'}), 500

if __name__ == '__main__':
    print(f"Flask server starting...")
    print(f"S3 Bucket: {BUCKET_NAME}")
    print("Available endpoints:")
    print("  POST /upload - Upload media with caption")
    print("  GET /media?current_user=username - Get media from other users") 
    print("  GET /user-media?username=username - Get media for specific user")
    print("  DELETE /delete-media - Delete user's media")
    print("  GET /health - Health check")
    
    app.run(host='0.0.0.0', port=8000, debug=True)