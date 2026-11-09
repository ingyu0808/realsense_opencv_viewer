"""RealSense 카메라 노드(align_depth 켬)와 OpenCV 뷰어를 함께 실행한다.

  ros2 launch realsense_opencv_viewer viewer.launch.py
  ros2 launch realsense_opencv_viewer viewer.launch.py launch_camera:=false   # 카메라는 따로 실행 중일 때

뷰어 창을 닫으면(q/ESC) launch 전체가 종료된다.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, Shutdown
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    args = [
        DeclareLaunchArgument('launch_camera', default_value='true',
                              description='realsense2_camera 노드도 함께 실행할지'),
        DeclareLaunchArgument('camera_ns', default_value='/camera',
                              description='카메라 토픽 앞부분 (realsense-ros 4.55 이상은 /camera/camera)'),
        DeclareLaunchArgument('display_scale', default_value='0.5', description='창 크기 배율'),
        DeclareLaunchArgument('save_path', default_value='',
                              description='지정하면 창 없이 한 장 저장하고 종료'),
    ]

    camera = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('realsense2_camera'), 'launch', 'rs_launch.py'])),
        launch_arguments={'align_depth.enable': 'true'}.items(),
        condition=IfCondition(LaunchConfiguration('launch_camera')),
    )

    viewer = Node(
        package='realsense_opencv_viewer',
        executable='rs_opencv_viewer',
        output='screen',
        parameters=[{
            'camera_ns': LaunchConfiguration('camera_ns'),
            'display_scale': LaunchConfiguration('display_scale'),
            'save_path': LaunchConfiguration('save_path'),
        }],
        on_exit=Shutdown(),
    )

    return LaunchDescription(args + [camera, viewer])
