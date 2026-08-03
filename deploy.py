import paramiko
import os
import tarfile
import sys
import time

HOST = "137.184.101.18"
PORT = 22
USER = "root"
PASSWORD = "b93322175803b787ee094381b9"
LOCAL_DIR = r"C:\Users\hulk cheng\.gemini\antigravity\scratch\byok_project"
TAR_FILE = "deploy_bundle.tar.gz"
REMOTE_DIR = "/root/byok_project"

def make_tarfile(output_filename, source_dir):
    print("Packaging deployment bundle...")
    def exclude_func(tarinfo):
        name = os.path.basename(tarinfo.name)
        if name in [".git", "node_modules", ".next", "__pycache__", TAR_FILE, "deploy.py", "venv", ".env"]:
            return None
        return tarinfo
        
    with tarfile.open(output_filename, "w:gz") as tar:
        for item in os.listdir(source_dir):
            if item in [".git", "node_modules", ".next", "__pycache__", TAR_FILE, "deploy.py", "venv", ".env"]:
                continue
            path = os.path.join(source_dir, item)
            tar.add(path, arcname=item, filter=exclude_func)
    print("Bundle created.")

def deploy():
    make_tarfile(TAR_FILE, LOCAL_DIR)
    
    import socks
    import socket
    proxy = socks.socksocket()
    proxy.settimeout(15)
    proxy.bind(('192.168.179.204', 0))
    proxy.set_proxy(socks.SOCKS5, '20.205.122.49', 21080, True, 'admin', '123456')
    
    print("Connecting to SOCKS5 Proxy (Bypassing TUN adapter)...")
    try:
        proxy.connect((HOST, PORT))
        print("Proxy connected! Authenticating via SSH...")
    except Exception as e:
        print(f"Proxy connection failed: {e}")
        return

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, sock=proxy, timeout=15)
    except Exception as e:
        print(f"SSH authentication failed: {e}")
        return

    print("Uploading bundle via SSH stream (SFTP is disabled)...")
    stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {REMOTE_DIR} && cat > {REMOTE_DIR}/{TAR_FILE}")
    with open(TAR_FILE, 'rb') as f:
        stdin.write(f.read())
    stdin.close()
    
    # Wait for upload to complete
    err = stderr.read().decode().strip()
    if err:
        print(f"Upload warning/error: {err}")
    print("Upload complete.")
    
    print("Extracting and building on remote server... This may take a few minutes.")
    commands = [
        f"cd {REMOTE_DIR}",
        f"tar -xzf {TAR_FILE}",
        "docker compose down",
        "docker compose build",
        "docker compose up -d"
    ]
    
    stdin, stdout, stderr = ssh.exec_command(" && ".join(commands))
    
    # Print output interactively
    while True:
        line = stdout.readline()
        if not line:
            break
        print(line.strip())
        
    for line in stderr:
        print(line.strip(), file=sys.stderr)
        
    ssh.close()
    print("Deployment finished successfully!")

if __name__ == "__main__":
    deploy()
