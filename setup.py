from glob import glob

from setuptools import find_packages, setup

package_name = 'realsense_opencv_viewer'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ingyu',
    maintainer_email='chldlsrbmoral05@gmail.com',
    description='RealSense ROS 2 topics to an OpenCV window via cv_bridge',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'rs_opencv_viewer = realsense_opencv_viewer.viewer_node:main',
        ],
    },
)
