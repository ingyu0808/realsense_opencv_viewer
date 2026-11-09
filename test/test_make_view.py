"""make_view() 단위 테스트 — 카메라 없이 합성 이미지로 확인한다."""
import numpy as np

from realsense_opencv_viewer.viewer_node import make_view

H, W = 48, 64


def frames(depth_mm):
    color = np.full((H, W, 3), 128, np.uint8)
    depth = np.full((H, W), depth_mm, np.uint16)
    return color, depth


def test_view_is_color_and_depth_side_by_side():
    color, depth = frames(1000)
    view = make_view(color, depth, (W // 2, H // 2), 0.001, 30)
    assert view.shape == (H, 2 * W, 3)
    assert view.dtype == np.uint8


def test_missing_depth_is_drawn_black():
    color, depth = frames(1000)
    depth[:10, :10] = 0
    view = make_view(color, depth, (W - 1, H - 1), 0.001, 30)
    assert view[0:10, W:W + 10].max() == 0          # depth 쪽 값 없는 영역
    assert view[20:30, W + 20:W + 30].max() > 0     # 값 있는 영역은 색이 칠해짐


def test_near_is_blue_far_is_red():
    near = make_view(*frames(200), (0, 0), 0.001, 30)[H - 1, W + W // 2]
    far = make_view(*frames(4800), (0, 0), 0.001, 30)[H - 1, W + W // 2]
    # OpenCV는 BGR: 가까우면 파랑(B)이 크고, 멀면 빨강(R)이 크다
    assert near[0] > near[2]
    assert far[2] > far[0]
