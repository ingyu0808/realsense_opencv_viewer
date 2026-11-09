"""RealSense ROS 2 토픽을 cv_bridge로 받아 OpenCV 창에 띄우는 노드.

컬러 이미지와 컬러 화면에 맞춘 depth(aligned depth)를 나란히 보여 주고,
마우스가 가리키는 점(기본: 화면 가운데)까지의 거리를 m 단위로 표시한다.

카메라 노드는 align_depth 를 켜고 실행해 두어야 한다:
  ros2 launch realsense2_camera rs_launch.py align_depth.enable:=true

파라미터:
  camera_ns      카메라 토픽 앞부분 (기본 /camera, realsense-ros 4.55 이상은 /camera/camera)
  depth_scale    depth 값 1이 몇 m인지 (기본 0.001 = mm)
  display_scale  창 크기 배율 (기본 0.5)
  save_path      지정하면 창 없이 1.5초 받은 뒤 이 경로에 PNG로 저장하고 종료
"""
import signal
import time

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from message_filters import ApproximateTimeSynchronizer, Subscriber
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Image

MAX_RANGE_M = 5.0      # depth 컬러맵에서 가장 먼 색(빨강)에 해당하는 거리
SAVE_AFTER_S = 1.5     # save_path 모드에서 FPS가 의미 있도록 기다리는 시간
WINDOW = 'RealSense: color | aligned depth  (q: quit)'


def make_view(color, depth, point, depth_scale, fps):
    """컬러 | depth 컬러맵을 나란히 붙이고 point 위치의 거리를 적은 BGR 이미지를 돌려준다."""
    h, w = depth.shape
    x, y = point
    dist_m = float(depth[y, x]) * depth_scale   # 0이면 그 점은 측정값 없음

    # depth(0 ~ MAX_RANGE_M)를 0 ~ 255로 바꿔 컬러맵 적용, 값이 없는 곳(0)은 검게
    alpha = 255.0 / (MAX_RANGE_M / depth_scale)
    depth_vis = cv2.applyColorMap(cv2.convertScaleAbs(depth, alpha=alpha), cv2.COLORMAP_JET)
    depth_vis[depth == 0] = 0

    view = np.hstack([color, depth_vis])
    for dx in (0, w):  # 컬러 쪽과 depth 쪽 같은 위치에 십자 표시
        cv2.drawMarker(view, (x + dx, y), (255, 255, 255), cv2.MARKER_CROSS, 30, 2)
    label = f'{dist_m:.3f} m' if dist_m > 0 else 'no depth'
    cv2.putText(view, label, (x + 15, y - 15), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
    cv2.putText(view, f'{fps} FPS  ({w}x{h})', (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2,
                (0, 255, 255), 3)
    return view


class RealSenseViewer(Node):
    def __init__(self):
        super().__init__('rs_opencv_viewer')
        ns = self.declare_parameter('camera_ns', '/camera').value.rstrip('/')
        self.depth_scale = self.declare_parameter('depth_scale', 0.001).value
        self.display_scale = self.declare_parameter('display_scale', 0.5).value
        self.save_path = self.declare_parameter('save_path', '').value

        self.bridge = CvBridge()
        self.color = None      # (H, W, 3) uint8, BGR
        self.depth = None      # (H, W) uint16, depth 단위 값 (D435i는 mm)
        self.updated = False
        self.stamps = []       # 최근 1초 동안 받은 시각 → FPS

        self.color_topic = f'{ns}/color/image_raw'
        self.depth_topic = f'{ns}/aligned_depth_to_color/image_raw'
        # QoS는 reliable(기본값, 큐 10)로 받는다. qos_profile_sensor_data(best effort)로 받으면
        # 1280x720 같은 큰 이미지가 전송 중 조각 하나만 잃어도 통째로 버려져 5 FPS 정도밖에 안 나온다.
        color_sub = Subscriber(self, Image, self.color_topic, qos_profile=10)
        depth_sub = Subscriber(self, Image, self.depth_topic, qos_profile=10)
        # 컬러와 depth는 따로 발행되므로, 시각이 50 ms 안쪽인 것끼리 짝지어 받는다
        sync = ApproximateTimeSynchronizer([color_sub, depth_sub], queue_size=10, slop=0.05)
        sync.registerCallback(self.on_frames)
        self.get_logger().info(f'구독: {self.color_topic}, {self.depth_topic}')

    def on_frames(self, color_msg, depth_msg):
        # sensor_msgs/Image → numpy 배열 (카메라는 rgb8로 보내므로 OpenCV용 bgr8로 변환)
        self.color = self.bridge.imgmsg_to_cv2(color_msg, 'bgr8')
        self.depth = self.bridge.imgmsg_to_cv2(depth_msg, 'passthrough')
        self.updated = True
        now = time.monotonic()
        self.stamps = [t for t in self.stamps if now - t < 1.0] + [now]

    def run(self):
        """프레임을 받아 그리는 메인 루프. 창을 닫거나 저장을 마치면 돌아온다."""
        mouse = {'pt': None}
        window_open = False
        start, warned, first_frame = time.monotonic(), False, None

        while rclpy.ok():
            rclpy.spin_once(self, timeout_sec=0.005)

            if self.color is None:
                if not warned and time.monotonic() - start > 5.0:
                    self.get_logger().warn(
                        f'{self.color_topic} 와 {self.depth_topic} 를 기다리는 중입니다. '
                        '카메라 노드를 align_depth.enable:=true 로 실행했는지, camera_ns 가 맞는지 확인하세요.')
                    warned = True
                continue

            if self.updated:
                self.updated = False
                h, w = self.depth.shape
                point = (w // 2, h // 2)
                if mouse['pt'] is not None:   # 창 좌표 → 원본 좌표 (depth 쪽을 가리켜도 같은 점)
                    mx, my = (int(v / self.display_scale) for v in mouse['pt'])
                    point = (min(mx % w, w - 1), min(my, h - 1))
                view = make_view(self.color, self.depth, point, self.depth_scale, len(self.stamps))

                if self.save_path:
                    first_frame = first_frame or time.monotonic()
                    if time.monotonic() - first_frame < SAVE_AFTER_S:
                        continue
                    cv2.imwrite(self.save_path, view)
                    self.get_logger().info(
                        f'저장: {self.save_path} ({view.shape[1]}x{view.shape[0]}, {len(self.stamps)} FPS)')
                    return
                if not window_open:
                    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
                    cv2.setMouseCallback(WINDOW, lambda ev, x, y, flags, param: mouse.update(pt=(x, y)))
                    window_open = True
                cv2.imshow(WINDOW, cv2.resize(view, None, fx=self.display_scale, fy=self.display_scale))

            if window_open:
                key = cv2.waitKey(1) & 0xFF
                # q/ESC로 종료. 창의 X 버튼으로 닫으면 속성 값이 -1이 된다.
                # (Ubuntu apt의 OpenCV 4.5.4(GTK)는 WND_PROP_VISIBLE을 지원하지 않아 항상 -1이므로 쓰지 않는다)
                if key in (ord('q'), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_AUTOSIZE) < 0:
                    return


def main(args=None):
    rclpy.init(args=args)
    node = RealSenseViewer()
    try:
        node.run()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        # ros2 launch 에서 Ctrl+C 를 누르면 터미널과 launch 가 각각 SIGINT 를 보내 두 번 들어온다.
        # 정리 도중 두 번째 SIGINT 로 KeyboardInterrupt 가 나지 않도록 이후 SIGINT 는 무시한다.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
