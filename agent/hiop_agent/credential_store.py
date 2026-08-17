from pathlib import Path

def save_credential(path:Path,credential:str)->None:
    try:
        import win32crypt
    except ImportError as exc:
        raise RuntimeError("Windows DPAPI support requires pywin32") from exc
    path.parent.mkdir(parents=True,exist_ok=True)
    encrypted=win32crypt.CryptProtectData(credential.encode(),"HIOP Local Agent",None,None,None,0)
    path.write_bytes(encrypted);path.chmod(0o600)

def load_credential(path:Path)->str:
    try:
        import win32crypt
    except ImportError as exc:
        raise RuntimeError("Windows DPAPI support requires pywin32") from exc
    if not path.exists():raise RuntimeError("Agent is not enrolled")
    return win32crypt.CryptUnprotectData(path.read_bytes(),None,None,None,0)[1].decode()
