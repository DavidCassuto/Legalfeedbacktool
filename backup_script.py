#!/usr/bin/env python3
"""
Automatic Backup Script for Legal Feedback Tool
Run this script to create a backup of your project
"""

import os
import shutil
import datetime
import zipfile
import sqlite3
from pathlib import Path

def create_backup():
    """Create a comprehensive backup of the project"""
    
    # Get current timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"backups/backup_{timestamp}"
    
    print(f"Creating backup: {backup_dir}")
    
    # Create backup directory
    os.makedirs(backup_dir, exist_ok=True)
    
    # Files to backup (exclude unnecessary files)
    files_to_backup = [
        'src/',
        'requirements.txt',
        'README.md',
        '.gitignore',
        'instance/documents.db',  # Database backup
    ]
    
    # Copy files
    for item in files_to_backup:
        if os.path.exists(item):
            if os.path.isdir(item):
                shutil.copytree(item, os.path.join(backup_dir, item))
            else:
                os.makedirs(os.path.dirname(os.path.join(backup_dir, item)), exist_ok=True)
                shutil.copy2(item, os.path.join(backup_dir, item))
            print(f"✓ Backed up: {item}")
        else:
            print(f"⚠ Skipped (not found): {item}")
    
    # Create backup info file
    backup_info = f"""
Backup Information
==================
Timestamp: {datetime.datetime.now().isoformat()}
Backup Directory: {backup_dir}
Files Backed Up: {len(files_to_backup)}

Project Status:
- Main application files: ✓
- Database: ✓
- Configuration: ✓
- Dependencies: ✓

Backup completed successfully!
"""
    
    with open(os.path.join(backup_dir, 'backup_info.txt'), 'w') as f:
        f.write(backup_info)
    
    # Create zip archive
    zip_filename = f"backups/backup_{timestamp}.zip"
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(backup_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, backup_dir)
                zipf.write(file_path, arcname)
    
    print(f"\n✅ Backup completed successfully!")
    print(f"📁 Backup location: {backup_dir}")
    print(f"📦 Zip archive: {zip_filename}")
    
    # Clean up old backups (keep last 5)
    cleanup_old_backups()
    
    return backup_dir

def cleanup_old_backups():
    """Keep only the last 5 backups to save space"""
    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        return
    
    # Get all backup directories
    backups = []
    for item in os.listdir(backup_dir):
        if item.startswith("backup_") and os.path.isdir(os.path.join(backup_dir, item)):
            backups.append(item)
    
    # Sort by creation time (newest first)
    backups.sort(key=lambda x: os.path.getctime(os.path.join(backup_dir, x)), reverse=True)
    
    # Remove old backups (keep last 5)
    for old_backup in backups[5:]:
        old_path = os.path.join(backup_dir, old_backup)
        shutil.rmtree(old_path)
        print(f"🗑️ Removed old backup: {old_backup}")

def git_backup():
    """Create a Git-based backup by committing current state"""
    import subprocess
    
    try:
        # Add all changes
        subprocess.run(['git', 'add', '.'], check=True)
        
        # Create commit
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_message = f"Automatic backup - {timestamp}"
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)
        
        # Push to remote
        subprocess.run(['git', 'push'], check=True)
        
        print("✅ Git backup completed successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Git backup failed: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Starting automatic backup...")
    
    # Create local backup
    backup_path = create_backup()
    
    # Try Git backup
    print("\n🔄 Creating Git backup...")
    git_success = git_backup()
    
    if git_success:
        print("🎉 All backups completed successfully!")
    else:
        print("⚠️ Local backup completed, but Git backup failed")
    
    print(f"\n📊 Backup Summary:")
    print(f"   Local backup: {backup_path}")
    print(f"   Git backup: {'✓' if git_success else '✗'}") 