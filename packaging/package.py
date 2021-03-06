import tempfile
from pathlib import Path
import tarfile
import logging
import shutil
import sys
import stat
import os
import platform

import coloredlogs

import conda.cli.python_api as Conda
from conda_build import api as CondaBuild
from conda_build.config import Config
from conda_pack import core as CondaPack

root = logging.getLogger()
root.setLevel(logging.INFO)

logger = logging.getLogger('hexrdgui')
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = coloredlogs.ColoredFormatter('%(asctime)s,%(msecs)03d - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

package_env_name = 'hexrd_package_env'

def patch_qt_config(base_path):
    logger.info('Patching qt.conf.')
    with (base_path / 'bin' / 'qt.conf').open('w') as fp:
        fp.write('[Paths]\n')
        fp.write('Plugins=../plugins')

def install_macos_script(base_path, package_path):
   # Add hexrd bash start script
    executable_path = package_path / 'hexrd'
    shutil.copyfile(base_path / 'darwin' / 'hexrd', executable_path)
    st = os.stat(executable_path)
    os.chmod(executable_path, st.st_mode | stat.S_IXUSR)

def build_mac_app_bundle(base_path, tar_path):
    package_path = base_path / 'package'
    package_path.mkdir()
    hexrd_app_path = package_path / 'HEXRD.app'
    hexrd_app_path.mkdir()
    hexrd_app_contents = hexrd_app_path / 'Contents'
    hexrd_app_contents.mkdir()
    hexrd_app_contents_macos = hexrd_app_contents / 'MacOS'
    hexrd_app_contents_macos.mkdir()
    hexrd_app_contents_resources = hexrd_app_contents / 'Resources'
    hexrd_app_contents_resources.mkdir()

    # Add Info.plist
    shutil.copyfile(base_path / 'darwin' / 'Info.plist', hexrd_app_contents / 'Info.plist')

    # Extract conda-pack tar into Resources/
    logger.info('Extracting tar into Resources/ directory.')
    tar = tarfile.open(tar_path)
    tar.extractall(path=hexrd_app_contents_resources)
    tar.close()

    patch_qt_config(hexrd_app_contents_resources)
    install_macos_script(base_path, hexrd_app_contents_macos)

def install_linux_script(base_path, package_path):
    logger.info('Generating hexrd script.')

    # First we rename the setuptools script
    hexrd_path = package_path / 'bin' / 'hexrd'
    hexrdgui_path = package_path / 'bin' / 'hexrdgui.py'
    hexrd_path.rename(hexrdgui_path)

    # Now install a shell script to call the setuptools script
    hexrd_executable = str(package_path / 'bin' / 'hexrd')
    shutil.copyfile(base_path / 'linux' / 'hexrd', hexrd_executable)
    st = os.stat(hexrd_executable)
    os.chmod(hexrd_executable, st.st_mode | stat.S_IXUSR)

def build_linux_package_dir(base_path, tar_path):
    logger.info('Extracting tar into package/ directory.')
    # Now extract the tar into to packge directory so it ready for cpack.
    package_path = base_path / 'package'
    package_path.mkdir(parents=True, exist_ok=True)
    tar = tarfile.open(tar_path)
    tar.extractall(path=package_path)
    tar.close()

    patch_qt_config(package_path)
    install_linux_script(base_path, package_path)

def build_conda_pack(base_path, tmp):
    # First build the hexrdgui package
    recipe_path = str(base_path / '..' / 'conda.recipe')
    config = Config()
    config.channel = ['cjh1', 'conda-forge']
    config.channel_urls = ['cjh1', 'conda-forge']
    logger.info('Building hexrd conda package.')
    CondaBuild.build(recipe_path, config=config)

    logger.info('Creating new conda environment.')
    # Now create a new environment to install the package into
    env_prefix = str(tmp / package_env_name)
    Conda.run_command(
        Conda.Commands.CREATE,
        '--prefix', env_prefix ,
        'python=3.7'
    )

    logger.info('Installing hexrdgui into new environment.')
    # Install hexrdgui into new environment
    params = [
        Conda.Commands.INSTALL,
        '--prefix', env_prefix,
        '--channel', 'cjh1',
        '--channel', 'conda-forge',
        '--use-local', 'hexrdgui'
    ]
    if platform.system() == 'Darwin':
        params.append('python.app=2')
    Conda.run_command(*params)

    logger.info('Generating tar from environment using conda-pack.')
    # Now use conda-pack to great relocatable tar
    tar_path = str(tmp / 'hexrdgui.tar')
    CondaPack.pack(
        prefix=env_prefix,
        output=tar_path,
        format='tar'
    )

    return tar_path

# We install a script that ensure the current working directory in
# the bin directory.
def install_windows_script(base_path, package_path):
    logger.info('Patch hexrd script.')

    # Now install a shell script to call the setuptools script
    hexrd_script = str(package_path / 'Scripts' / 'hexrd-script.py')
    shutil.copyfile(base_path / 'windows' / 'hexrd-script.py', hexrd_script)

def patch_qt_config_windows(base_path):
    logger.info('Patching qt.conf.')
    with (base_path / 'qt.conf').open('w') as fp:
        fp.write('[Paths]\n')
        fp.write('Prefix = Library\n')
        fp.write('Binaries = Library/bin\n')
        fp.write('Libraries = Library/lib\n')
        fp.write('Headers = Library/include/qt\n')
        fp.write('TargetSpec = win32-msvc\n')
        fp.write('HostSpec = win32-msvc\n')

def build_windows_package_dir(base_path, tar_path):
    logger.info('Extracting tar into package/ directory.')
    # Now extract the tar into to packge directory so it ready for cpack.
    package_path = base_path / 'package'
    package_path.mkdir(parents=True, exist_ok=True)
    tar = tarfile.open(tar_path)
    tar.extractall(path=package_path)
    tar.close()

    patch_qt_config_windows(package_path)
    install_windows_script(base_path, package_path)

def build_package():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        base_path = Path(__file__).parent
        tar_path = build_conda_pack(base_path, tmp)

        package_path = base_path / 'package'
        # Remove first so we start fresh
        shutil.rmtree(str(package_path), ignore_errors=True)

        if platform.system() == 'Darwin':
            build_mac_app_bundle(base_path, tar_path)
        elif platform.system() == 'Linux':
            build_linux_package_dir(base_path, tar_path)
        elif platform.system() == 'Windows':
            build_windows_package_dir(base_path, tar_path)
        else:
            raise Exception('Unsupported platform: %s' % platform.system())

if __name__ == '__main__':
    build_package()