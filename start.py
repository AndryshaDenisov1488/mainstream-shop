#!/usr/bin/env python3
"""
Simple startup script for MainStream Shop
"""

import os
import sys
import subprocess

def main():
    print("🚀 Starting MainStream Shop...")
    
    # Set environment variables for UTF-8
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'
    
    # Check if virtual environment exists
    if not os.path.exists('venv'):
        print("Creating virtual environment...")
        subprocess.run([sys.executable, '-m', 'venv', 'venv'])
    
    # Determine the correct Python executable
    if os.name == 'nt':  # Windows
        python_exe = os.path.join('venv', 'Scripts', 'python.exe')
    else:  # Unix/Linux/Mac
        python_exe = os.path.join('venv', 'bin', 'python')
    
    if not os.path.exists(python_exe):
        print(f"Virtual environment Python not found at {python_exe}")
        print("Please run the setup manually:")
        print("1. python -m venv venv")
        print("2. venv\\Scripts\\activate (Windows) or source venv/bin/activate (Unix)")
        print("3. pip install -r requirements.txt")
        print("4. python run_local.py")
        return
    
    # Check if dependencies are installed
    try:
        import flask
        print("✅ Dependencies already installed")
    except ImportError:
        print("Installing dependencies...")
        subprocess.run([python_exe, '-m', 'pip', 'install', '-r', 'requirements.txt'])
    
    # Create .env file if it doesn't exist
    if not os.path.exists('.env'):
        print("Creating .env file...")
        if os.path.exists('env.example'):
            with open('env.example', 'r', encoding='utf-8') as src:
                with open('.env', 'w', encoding='utf-8') as dst:
                    dst.write(src.read())
    
    # Create logs directory
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    print("\n🌐 Starting MainStream Shop...")
    print("Open http://localhost:5000 in your browser")
    print("\nTest accounts:")
    print("  Admin: admin@mainstreamfs.ru / admin123")
    print("  Customer: customer@test.ru / customer123")
    print("  Operator: operator@test.ru / operator123")
    print("  Mom: mom@test.ru / mom123")
    print("\n" + "="*50)
    
    # Start the application
    subprocess.run([python_exe, 'run_local.py'])

if __name__ == '__main__':
    main()
