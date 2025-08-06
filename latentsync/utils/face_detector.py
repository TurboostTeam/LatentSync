from insightface.app import FaceAnalysis
import numpy as np
import torch

INSIGHTFACE_DETECT_SIZE = 512


class FaceDetector:
    def __init__(self, device="cuda"):
        self.app = FaceAnalysis(
            allowed_modules=["detection", "landmark_2d_106"],
            root="checkpoints/auxiliary",
            providers=["CUDAExecutionProvider"],
        )
        self.app.prepare(ctx_id=cuda_to_int(device), det_size=(INSIGHTFACE_DETECT_SIZE, INSIGHTFACE_DETECT_SIZE))

    def _is_face_suitable(self, face, frame_shape):
        """
        An internal helper function to check whether a detected face is suitable for lip synchronization.
        It integrates several filtering strategies.

        :param face: The single face object returned by insightface.
        :param frame_shape: The shape of the original video frame (h, w, c).
        
        :return: bool, True if the face is suitable, False otherwise.
        """
        f_h, f_w, _ = frame_shape
        lmk = np.round(face.landmark_2d_106).astype(np.int_)

        # filter lip edge case based on lip corner distance
        lip_center = np.mean([lmk[71], lmk[53]], axis=0)
        left_corner_dist = np.linalg.norm(lmk[52] - lip_center)
        right_corner_dist = np.linalg.norm(lmk[61] - lip_center)
        min_dist = min(left_corner_dist, right_corner_dist)
        max_dist = max(left_corner_dist, right_corner_dist)

        if min_dist < max_dist * 0.2:
            return False

        # filter out-of-screen case based on nose key points
        nose_indices = [73, 74, 86, 76, 77,  80, 82, 83]
        nose_left = min([lmk[i][0] for i in nose_indices])
        nose_right = max([lmk[i][0] for i in nose_indices])
        margin_screen = 5 # smaller margin for boundary tolerance

        if nose_left <= 0 + margin_screen or nose_right >= f_w - margin_screen:
            return False

        # filter side face case based on cheek key points
        cheek_indices = [12, 14, 16, 3, 5, 7, 0, 23, 21, 19, 32, 30, 28]
        cheek_left = np.min(lmk[cheek_indices][:, 0])
        cheek_right = np.max(lmk[cheek_indices][:, 0])
        margin_cheek = 5 # smaller margin for boundary tolerance

        if nose_left < cheek_left + margin_cheek or nose_right > cheek_right - margin_cheek:
            return False

        return True


    def __call__(self, frame, threshold=0.5):
        f_h, f_w, _ = frame.shape

        faces = self.app.get(frame)

        get_face_store = None
        max_size = 0

        if len(faces) == 0:
            return None, None
        else:
            for face in faces:
                bbox = face.bbox.astype(np.int_).tolist()
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                if w < 50 or h < 80:
                    continue
                if w / h > 1.5 or w / h < 0.2:
                    continue
                if face.det_score < threshold:
                    continue

                if not self._is_face_suitable(face, frame.shape):
                    continue

                size_now = w * h

                if size_now > max_size:
                    max_size = size_now
                    get_face_store = face

        if get_face_store is None:
            return None, None
        else:
            face = get_face_store
            lmk = np.round(face.landmark_2d_106).astype(np.int_)

            halk_face_coord = np.mean([lmk[74], lmk[73]], axis=0)  # lmk[73]

            sub_lmk = lmk[LMK_ADAPT_ORIGIN_ORDER]
            halk_face_dist = np.max(sub_lmk[:, 1]) - halk_face_coord[1]
            upper_bond = halk_face_coord[1] - halk_face_dist  # *0.94

            x1, y1, x2, y2 = (np.min(sub_lmk[:, 0]), int(upper_bond), np.max(sub_lmk[:, 0]), np.max(sub_lmk[:, 1]))

            if y2 - y1 <= 0 or x2 - x1 <= 0 or x1 < 0:
                x1, y1, x2, y2 = face.bbox.astype(np.int_).tolist()

            y2 += int((x2 - x1) * 0.1)
            x1 -= int((x2 - x1) * 0.05)
            x2 += int((x2 - x1) * 0.05)

            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(f_w, x2)
            y2 = min(f_h, y2)

            return (x1, y1, x2, y2), lmk


def cuda_to_int(cuda_str: str) -> int:
    """
    Convert the string with format "cuda:X" to integer X.
    """
    if cuda_str == "cuda":
        return 0
    device = torch.device(cuda_str)
    if device.type != "cuda":
        raise ValueError(f"Device type must be 'cuda', got: {device.type}")
    return device.index


LMK_ADAPT_ORIGIN_ORDER = [
    1, 10, 12, 14, 16, 3, 5, 7, # left cheek
    0, # chin
    23, 21, 19, 32, 30, 28, 26, 17, # right cheek
    43, 48, 49, 51, 50, # left eyebrow
    102, 103, 104, 105, 101, # right eyebrow
    73, 74, 86, # nose
]
