"""Build the credential-free Windows download shipped with the backend."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
destination = root / 'backend/app/distributions/hiop-agent-windows.zip'
destination.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
    sources = sorted((root / 'agent/hiop_agent').glob('*.py'))
    sources += [root / 'agent/install-user.ps1', root / 'agent/Connect HIOP.cmd']
    for path in sources:
        archive.write(path, str(path.relative_to(root / 'agent')))
print('Built Windows agent download')
