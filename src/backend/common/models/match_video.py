from typing import TypedDict

from backend.common.consts.media_type import VideoType


class MatchVideo(TypedDict):
    type: VideoType
    key: str
