from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
import os
from datetime import datetime
import uuid

app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clouddrive.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['JWT_SECRET_KEY'] = 'jwtsecretkey'
app.config['UPLOAD_FOLDER'] = 'uploads'

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(200), nullable=True, default='default-avatar.png')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(200), nullable=True)
    file_type = db.Column(db.String(50), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_starred = db.Column(db.Boolean, default=False)
    parent_folder_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=True)

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    files = db.relationship('File', backref='folder', lazy=True)
    subfolders = db.relationship('Folder', backref=db.backref('parent', remote_side=[id]), lazy=True)

class SharedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('file.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    shared_with_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    share_link = db.Column(db.String(200), unique=True, nullable=False)
    can_edit = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
with app.app_context():
    db.create_all()

# User Registration
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"message": "Username already exists"}), 400
    if User.query.filter_by(email=data['email']).first():
        return jsonify({"message": "Email already exists"}), 400
        
    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    new_user = User(
        username=data['username'],
        email=data['email'],
        password=hashed_password
    )
    db.session.add(new_user)
    db.session.commit()
    
    # Create root folder for new user
    root_folder = Folder(name="My Drive", user_id=new_user.id)
    db.session.add(root_folder)
    db.session.commit()
    
    return jsonify({"message": "Registration complete!", "user_id": new_user.id})

# User Login
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    
    if user and bcrypt.check_password_hash(user.password, data['password']):
        access_token = create_access_token(identity=user.id)
        return jsonify({
            "token": access_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "avatar": user.avatar
            }
        })
    return jsonify({"message": "Invalid username or password"}), 401

# Get user info
@app.route('/user', methods=['GET'])
@jwt_required()
def get_user_info():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "avatar": user.avatar
    })

# File Upload
@app.route('/files', methods=['POST'])
@jwt_required()
def upload_file():
    user_id = get_jwt_identity()
    
    if 'file' not in request.files:
        return jsonify({"message": "No file part"}), 400
        
    file = request.files['file']
    title = request.form.get('title', file.filename)
    content = request.form.get('content', '')
    folder_id = request.form.get('folder_id', None)
    
    if file.filename == '':
        return jsonify({"message": "No file selected"}), 400
        
    file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    filename = f"{uuid.uuid4().hex}.{file_ext}" if file_ext else f"{uuid.uuid4().hex}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file_size = 0
    
    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)
    except Exception as e:
        return jsonify({"message": f"Error saving file: {str(e)}"}), 500
    
    new_file = File(
        title=title,
        content=content,
        file_path=file_path,
        file_type=file_ext,
        file_size=file_size,
        user_id=user_id,
        parent_folder_id=folder_id
    )
    
    db.session.add(new_file)
    db.session.commit()
    
    return jsonify({
        "message": "File uploaded successfully!",
        "file": {
            "id": new_file.id,
            "title": new_file.title,
            "file_path": new_file.file_path,
            "file_type": new_file.file_type,
            "file_size": new_file.file_size
        }
    })

# Get files
@app.route('/files', methods=['GET'])
@jwt_required()
def get_files():
    user_id = get_jwt_identity()
    folder_id = request.args.get('folder_id', None)
    
    if folder_id:
        files = File.query.filter_by(user_id=user_id, parent_folder_id=folder_id).all()
    else:
        files = File.query.filter_by(user_id=user_id).all()
    
    files_list = [{
        "id": file.id,
        "title": file.title,
        "content": file.content,
        "file_path": file.file_path,
        "file_type": file.file_type,
        "file_size": file.file_size,
        "created_at": file.created_at.isoformat(),
        "updated_at": file.updated_at.isoformat(),
        "is_starred": file.is_starred,
        "folder_id": file.parent_folder_id
    } for file in files]
    
    return jsonify(files_list)

# Get starred files
@app.route('/files/starred', methods=['GET'])
@jwt_required()
def get_starred_files():
    user_id = get_jwt_identity()
    files = File.query.filter_by(user_id=user_id, is_starred=True).all()
    
    files_list = [{
        "id": file.id,
        "title": file.title,
        "content": file.content,
        "file_path": file.file_path,
        "file_type": file.file_type,
        "file_size": file.file_size,
        "created_at": file.created_at.isoformat(),
        "updated_at": file.updated_at.isoformat(),
        "is_starred": file.is_starred,
        "folder_id": file.parent_folder_id
    } for file in files]
    
    return jsonify(files_list)

# Star/Unstar file
@app.route('/files/<int:id>/star', methods=['POST'])
@jwt_required()
def star_file(id):
    user_id = get_jwt_identity()
    file = File.query.filter_by(id=id, user_id=user_id).first()
    
    if not file:
        return jsonify({"message": "File not found"}), 404
        
    file.is_starred = not file.is_starred
    db.session.commit()
    
    return jsonify({
        "message": f"File {'starred' if file.is_starred else 'unstarred'} successfully",
        "is_starred": file.is_starred
    })

# Edit file
@app.route('/files/<int:id>', methods=['PUT'])
@jwt_required()
def edit_file(id):
    user_id = get_jwt_identity()
    data = request.json
    file = File.query.filter_by(id=id, user_id=user_id).first()
    
    if not file:
        # Check if file is shared with edit permissions
        shared_file = SharedFile.query.filter_by(file_id=id, shared_with_id=user_id, can_edit=True).first()
        if not shared_file:
            return jsonify({"message": "File not found or you don't have permission to edit"}), 404
        file = File.query.get(id)
    
    if file:
        file.title = data.get('title', file.title)
        file.content = data.get('content', file.content)
        file.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({
            "message": "File updated successfully!",
            "file": {
                "id": file.id,
                "title": file.title,
                "content": file.content,
                "updated_at": file.updated_at.isoformat()
            }
        })
        
    return jsonify({"message": "File not found!"}), 404

# View file
@app.route('/files/<int:id>', methods=['GET'])
@jwt_required()
def view_file(id):
    user_id = get_jwt_identity()
    file = File.query.filter_by(id=id, user_id=user_id).first()
    
    # If not user's file, check if shared with user
    if not file:
        shared_file = SharedFile.query.filter_by(file_id=id, shared_with_id=user_id).first()
        # Also check if it's a publicly shared file
        if not shared_file:
            share_link = request.args.get('share_link')
            if share_link:
                shared_file = SharedFile.query.filter_by(file_id=id, share_link=share_link).first()
                
        if shared_file:
            file = File.query.get(id)
        else:
            return jsonify({"message": "File not found or you don't have permission to view"}), 404
    
    if file:
        file_data = {
            "id": file.id,
            "title": file.title,
            "content": file.content,
            "file_path": file.file_path,
            "file_type": file.file_type,
            "file_size": file.file_size,
            "created_at": file.created_at.isoformat(),
            "updated_at": file.updated_at.isoformat(),
            "is_starred": file.is_starred,
            "folder_id": file.parent_folder_id
        }
        return jsonify(file_data)
        
    return jsonify({"message": "File not found!"}), 404

# Download file
@app.route('/download/<int:id>', methods=['GET'])
@jwt_required()
def download_file(id):
    user_id = get_jwt_identity()
    file = File.query.filter_by(id=id, user_id=user_id).first()
    
    # If not user's file, check if shared with user
    if not file:
        shared_file = SharedFile.query.filter_by(file_id=id, shared_with_id=user_id).first()
        # Also check if it's a publicly shared file
        if not shared_file:
            share_link = request.args.get('share_link')
            if share_link:
                shared_file = SharedFile.query.filter_by(file_id=id, share_link=share_link).first()
                
        if shared_file:
            file = File.query.get(id)
        else:
            return jsonify({"message": "File not found or you don't have permission to download"}), 404
    
    if file and file.file_path:
        directory = os.path.dirname(file.file_path)
        filename = os.path.basename(file.file_path)
        return send_from_directory(directory, filename, as_attachment=True, download_name=file.title)
        
    return jsonify({"message": "File not found!"}), 404

# Create folder
@app.route('/folders', methods=['POST'])
@jwt_required()
def create_folder():
    user_id = get_jwt_identity()
    data = request.json
    name = data.get('name', 'New Folder')
    parent_id = data.get('parent_id')
    
    new_folder = Folder(
        name=name,
        user_id=user_id,
        parent_id=parent_id
    )
    
    db.session.add(new_folder)
    db.session.commit()
    
    return jsonify({
        "message": "Folder created successfully!",
        "folder": {
            "id": new_folder.id,
            "name": new_folder.name,
            "parent_id": new_folder.parent_id,
            "created_at": new_folder.created_at.isoformat()
        }
    })

# Get folders
@app.route('/folders', methods=['GET'])
@jwt_required()
def get_folders():
    user_id = get_jwt_identity()
    parent_id = request.args.get('parent_id')
    
    if parent_id:
        folders = Folder.query.filter_by(user_id=user_id, parent_id=parent_id).all()
    else:
        folders = Folder.query.filter_by(user_id=user_id).all()
    
    folders_list = [{
        "id": folder.id,
        "name": folder.name,
        "parent_id": folder.parent_id,
        "created_at": folder.created_at.isoformat(),
        "updated_at": folder.updated_at.isoformat()
    } for folder in folders]
    
    return jsonify(folders_list)

# Rename folder
@app.route('/folders/<int:id>', methods=['PUT'])
@jwt_required()
def rename_folder(id):
    user_id = get_jwt_identity()
    data = request.json
    folder = Folder.query.filter_by(id=id, user_id=user_id).first()
    
    if folder:
        folder.name = data.get('name', folder.name)
        folder.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({
            "message": "Folder renamed successfully!",
            "folder": {
                "id": folder.id,
                "name": folder.name,
                "updated_at": folder.updated_at.isoformat()
            }
        })
        
    return jsonify({"message": "Folder not found!"}), 404

# Get folder contents
@app.route('/folders/<int:id>/contents', methods=['GET'])
@jwt_required()
def get_folder_contents(id):
    user_id = get_jwt_identity()
    folder = Folder.query.filter_by(id=id, user_id=user_id).first()
    
    if not folder:
        return jsonify({"message": "Folder not found!"}), 404
    
    subfolders = Folder.query.filter_by(parent_id=id).all()
    files = File.query.filter_by(parent_folder_id=id).all()
    
    subfolders_list = [{
        "id": subfolder.id,
        "name": subfolder.name,
        "parent_id": subfolder.parent_id,
        "created_at": subfolder.created_at.isoformat(),
        "updated_at": subfolder.updated_at.isoformat(),
        "type": "folder"
    } for subfolder in subfolders]
    
    files_list = [{
        "id": file.id,
        "title": file.title,
        "file_type": file.file_type,
        "file_size": file.file_size,
        "created_at": file.created_at.isoformat(),
        "updated_at": file.updated_at.isoformat(),
        "is_starred": file.is_starred,
        "type": "file"
    } for file in files]
    
    contents = subfolders_list + files_list
    
    return jsonify({
        "folder": {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id
        },
        "contents": contents
    })

# Share file
@app.route('/files/<int:id>/share', methods=['POST'])
@jwt_required()
def share_file(id):
    user_id = get_jwt_identity()
    data = request.json
    file = File.query.filter_by(id=id, user_id=user_id).first()
    
    if not file:
        return jsonify({"message": "File not found!"}), 404
    
    shared_with_username = data.get('shared_with_username')
    can_edit = data.get('can_edit', False)
    
    # Generate unique share link
    share_link = f"{uuid.uuid4().hex}"
    
    if shared_with_username:
        shared_user = User.query.filter_by(username=shared_with_username).first()
        if not shared_user:
            return jsonify({"message": "User not found!"}), 404
            
        # Check if already shared with this user
        existing_share = SharedFile.query.filter_by(
            file_id=id, 
            owner_id=user_id, 
            shared_with_id=shared_user.id
        ).first()
        
        if existing_share:
            existing_share.can_edit = can_edit
            db.session.commit()
            return jsonify({
                "message": "Sharing permissions updated!",
                "share_link": existing_share.share_link
            })
            
        shared_file = SharedFile(
            file_id=id,
            owner_id=user_id,
            shared_with_id=shared_user.id,
            share_link=share_link,
            can_edit=can_edit
        )
    else:
        # Public sharing without specific user
        shared_file = SharedFile(
            file_id=id,
            owner_id=user_id,
            share_link=share_link,
            can_edit=can_edit
        )
    
    db.session.add(shared_file)
    db.session.commit()
    
    return jsonify({
        "message": "File shared successfully!",
        "share_link": f"{request.host_url}shared/{share_link}"
    })

# Get shared files
@app.route('/shared', methods=['GET'])
@jwt_required()
def get_shared_files():
    user_id = get_jwt_identity()
    
    # Files shared by the user
    shared_by_me = SharedFile.query.filter_by(owner_id=user_id).all()
    shared_by_me_files = []
    
    for share in shared_by_me:
        file = File.query.get(share.file_id)
        if file:
            shared_with = None
            if share.shared_with_id:
                shared_user = User.query.get(share.shared_with_id)
                if shared_user:
                    shared_with = shared_user.username
            
            shared_by_me_files.append({
                "id": file.id,
                "title": file.title,
                "file_type": file.file_type,
                "shared_with": shared_with,
                "can_edit": share.can_edit,
                "share_link": f"{request.host_url}shared/{share.share_link}",
                "shared_at": share.created_at.isoformat()
            })
    
    # Files shared with the user
    shared_with_me = SharedFile.query.filter_by(shared_with_id=user_id).all()
    shared_with_me_files = []
    
    for share in shared_with_me:
        file = File.query.get(share.file_id)
        owner = User.query.get(share.owner_id)
        
        if file and owner:
            shared_with_me_files.append({
                "id": file.id,
                "title": file.title,
                "file_type": file.file_type,
                "owner": owner.username,
                "can_edit": share.can_edit,
                "shared_at": share.created_at.isoformat()
            })
    
    return jsonify({
        "shared_by_me": shared_by_me_files,
        "shared_with_me": shared_with_me_files
    })

# Access shared file via link
@app.route('/shared/<share_link>', methods=['GET'])
def access_shared_file(share_link):
    shared_file = SharedFile.query.filter_by(share_link=share_link).first()
    
    if not shared_file:
        return jsonify({"message": "Invalid share link!"}), 404
        
    file = File.query.get(shared_file.file_id)
    owner = User.query.get(shared_file.owner_id)
    
    if not file or not owner:
        return jsonify({"message": "File not found!"}), 404
        
    return jsonify({
        "file": {
            "id": file.id,
            "title": file.title,
            "content": file.content,
            "file_type": file.file_type,
            "file_size": file.file_size,
            "owner": owner.username,
            "can_edit": shared_file.can_edit
        }
    })

if __name__ == '__main__':
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
    app.run(debug=True)
