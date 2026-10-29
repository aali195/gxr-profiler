"""Media, audio and display sampling (always on, low frequency)."""

from __future__ import annotations

import logging

from ..core import parsers as P
from ..core.adb import AdbClient

log = logging.getLogger(__name__)

MEDIA_SCRIPT = (
    "echo '###MEDIA'; dumpsys media.metrics 2>/dev/null "
    "| grep -E 'android.media.mediacodec.mode=(video|audio)' | tail -20; "
    "echo '###RESOURCES'; dumpsys media.resource_manager 2>/dev/null "
    "| grep -E '^  Processes:|^    Pid:|^      Client:|^        Id:|^        Name:|"
    "video-codec|^  Events logs|addMediaInfo'; "
    "echo '###DISPLAY'; dumpsys display 2>/dev/null "
    "| grep -E 'Display Brightness=|Display SdrBrightness=|mBrightnessState='; "
    "echo '###SFHDR'; dumpsys SurfaceFlinger 2>/dev/null "
    "| grep -E '^\\* Layer|composition type=|dataspace=|format:|Current color mode:'; "
    "echo '###AUDIO'; dumpsys audio 2>/dev/null; "
    "echo '###FLINGER'; dumpsys media.audio_flinger 2>/dev/null "
    "| grep -E '^(Output|Input) thread|^[[:space:]]+(Standby:|Sample rate:|HAL format:|"
    "Channel count:|Output devices:|Input device:|Audio source:|Master volume:|Master mute:|"
    "Normal mixer raw underrun counters:|Threadloop write latency stats:|Process time ms stats:|"
    "Timestamp stats:|[0-9]+ Tracks of which)'"
)


class MediaSampler:
    def __init__(self, adb: AdbClient) -> None:
        self.adb = adb
        self._media_seen: set[str] = set()

    def poll(self, now: float, t0: float | None, dev_baseline: float | None) -> dict:
        try:
            text = self.adb.shell(MEDIA_SCRIPT, timeout=25.0)
        except Exception:
            log.debug("media poll failed", exc_info=True)
            return {"media_poll_ok": 0.0}

        sec = P.split_sections(text)
        video = P.parse_media_video(sec.get("MEDIA", []))
        audio_codec = P.parse_media_audio(sec.get("MEDIA", []))
        active = P.parse_media_resources(sec.get("RESOURCES", []))
        st: dict = {"media_poll_ok": 1.0}

        # media.metrics only records completed/flushed sessions. Keep its last
        # values for the history columns, but determine the live decoder from
        # ResourceManager's current video-codec allocation.
        if video:
            st.update(video)
        st["media_active"] = 0.0
        if active:
            active_codec = active.get("media_codec")
            if video.get("media_codec") and video.get("media_codec") != active_codec:
                # Do not attach app/MIME/profile/resolution from an older codec
                # session to the currently allocated decoder.
                for key in (
                    "media_app",
                    "media_mime",
                    "media_profile",
                    "media_hdr_format",
                    "media_bit_depth",
                    "media_id",
                ):
                    st[key] = None
            st.update(active)
        name = st.get("media_codec")
        if name:
            self._media_seen.add(name)
            st["media_codecs"] = ",".join(sorted(self._media_seen))
        if not active:
            st["media_hw_dec"] = 0.0
            st["media_sw_dec"] = 0.0

        st.update(P.parse_display_props("\n".join(sec.get("DISPLAY", []))))
        sf = P.visible_sf_lines(sec.get("SFHDR", []))
        hdr = P.hdr_from_dataspaces(sf)
        depth = P.bit_depth_from_formats(sf)
        st["disp_bit_depth"] = depth
        st["disp_color_mode"] = P.color_mode_from_lines(sf)
        st["hdr_active"] = 1.0 if hdr else 0.0
        if active and (st.get("media_hdr_format") or 0) > 0:
            st["media_bit_depth"] = 10.0

        ts = audio_codec.pop("audio_codec_ts", None)
        if ts is not None and dev_baseline is not None and t0 is not None:
            age = dev_baseline + (now - t0) - ts
            if age < -183 * 86400:
                age += 365 * 86400
            elif age > 183 * 86400:
                age -= 365 * 86400
            if age >= 0:
                audio_codec["audio_codec_age_s"] = round(age, 1)
        st.update(audio_codec)

        audio = P.parse_audio_state("\n".join(sec.get("AUDIO", [])))
        fl = P.parse_audio_flinger("\n".join(sec.get("FLINGER", [])))
        music_mute = audio.get("audio_out_mute")
        fl_mute = fl.get("audio_out_mute")
        if music_mute is not None or fl_mute is not None:
            fl["audio_out_mute"] = 1.0 if (music_mute or fl_mute) else 0.0
        st.update(audio)
        st.update(fl)
        return st
