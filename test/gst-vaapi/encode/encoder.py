###
### Copyright (C) 2018-2019 Intel Corporation
###
### SPDX-License-Identifier: BSD-3-Clause
###

from ....lib import *
from ..util import *

@slash.requires(have_gst)
@slash.requires(*have_gst_element("vaapi"))
@slash.requires(*have_gst_element("checksumsink2"))
class EncoderTest(slash.Test):
  def gen_input_opts(self):
    opts = "filesrc location={source} num-buffers={frames}"
    opts += " ! rawvideoparse format={mformat} width={width} height={height}"

    if vars(self).get("fps", None) is not None:
      opts += " framerate={fps}"

    opts += " ! videoconvert ! video/x-raw,format={hwformat}"

    return opts.format(**vars(self))

  def gen_output_opts(self):
    opts = "{gstencoder}"

    if self.codec not in ["jpeg",]:
      opts += " rate-control={rcmode}"

    if vars(self).get("gop", None) is not None:
      opts += " keyframe-period={gop}"
    if vars(self).get("qp", None) is not None:
      if self.codec in ["vp8", "vp9",]:
        opts += " yac-qi={qp}"
      elif self.codec in ["mpeg2"]:
        opts += " quantizer={mqp}"
      else:
        opts += " init-qp={qp}"
    if vars(self).get("quality", None) is not None:
      if self.codec in ["jpeg",]:
        opts += " quality={quality}"
      else:
        opts += " quality-level={quality}"
    if vars(self).get("slices", None) is not None:
      opts += " num-slices={slices}"
    if vars(self).get("bframes", None) is not None:
      opts += " max-bframes={bframes}"
    if vars(self).get("maxrate", None) is not None:
      opts += " bitrate={maxrate}"
    if vars(self).get("refmode", None) is not None:
      opts += " ref-pic-mode={refmode}"
    if vars(self).get("refs", None) is not None:
      opts += " refs={refs}"
    if vars(self).get("lowpower", False):
      opts += " tune=low-power"
    if vars(self).get("lowdelayb",False):
      opts += " low-delay-b=1"
    if vars(self).get("loopshp", None) is not None:
      opts += " sharpness-level={loopshp}"
    if vars(self).get("looplvl", None) is not None:
      opts += " loop-filter-level={looplvl}"

    if self.codec not in ["jpeg", "mpeg2", "vp8", "vp9",]:
      opts += " ! {gstmediatype},profile={mprofile}"

    if vars(self).get("gstparser", None) is not None:
      opts += " ! {gstparser}"

    if vars(self).get("gstmuxer", None) is not None:
      opts += " ! {gstmuxer}"

    opts += " ! filesink location={encoded}"

    return opts.format(**vars(self))

  def gen_name(self):
    name = "{case}-{rcmode}-{profile}"
    if vars(self).get("fps", None) is not None:
      name += "-{fps}"
    if vars(self).get("gop", None) is not None:
      name += "-{gop}"
    if vars(self).get("qp", None) is not None:
      name += "-{qp}"
    if vars(self).get("slices", None) is not None:
      name += "-{slices}"
    if vars(self).get("quality", None) is not None:
      name += "-{quality}"
    if vars(self).get("bframes", None) is not None:
      name += "-{bframes}"
    if vars(self).get("minrate", None) is not None:
      name += "-{minrate}k"
    if vars(self).get("maxrate", None) is not None:
      name += "-{maxrate}k"
    if vars(self).get("refmode", None) is not None:
      name += "-{refmode}"
    if vars(self).get("refs", None) is not None:
      name += "-{refs}"
    if vars(self).get("lowpower", False):
      name += "-low-power"
    if vars(self).get("loopshp", None) is not None:
      name += "-{loopshp}"
    if vars(self).get("looplvl", None) is not None:
      name += "-{looplvl}"
    return name.format(**vars(self))

  def before(self):
    self.refctx = []

  def encode(self):
    self.mprofile = mapprofile(self.codec, self.profile)
    if self.mprofile is None:
      slash.skip_test("{profile} profile is not supported".format(**vars(self)))

    self.mformat = mapformat(self.format)
    self.mformatu = mapformatu(self.format)
    self.hwformat = mapformat_hwup(self.format)
    if self.mformat is None:
      slash.skip_test("{format} format not supported".format(**vars(self)))

    self.encoded = get_media()._test_artifact(
      "{}.{}".format(self.gen_name(), self.get_file_ext()))

    iopts = self.gen_input_opts()
    oopts = self.gen_output_opts()

    self.output = call(
      "gst-launch-1.0 -vf"
      " {iopts} ! {oopts}".format(iopts = iopts, oopts = oopts)
    )

    self.check_bitrate()
    self.check_metrics()

  def check_metrics(self):
    self.decoded = get_media()._test_artifact(
      "{}-{width}x{height}-{format}.yuv".format(self.gen_name(), **vars(self)))

    call(
      "gst-launch-1.0 -vf filesrc location={encoded}"
      " ! {gstdecoder}"
      " ! videoconvert ! video/x-raw,format={mformatu}"
      " ! checksumsink2 file-checksum=false frame-checksum=false"
      " plane-checksum=false dump-output=true qos=false"
      " dump-location={decoded}".format(**vars(self))
    )

    get_media().baseline.check_psnr(
      psnr = calculate_psnr(
        self.source, self.decoded,
        self.width, self.height,
        self.frames, self.format),
      context = self.refctx,
    )

  def check_bitrate(self):
    if "cbr" == self.rcmode:
      encsize = os.path.getsize(self.encoded)
      bitrate_actual = encsize * 8 * self.fps / 1024.0 / self.frames
      bitrate_gap = abs(bitrate_actual - self.bitrate) / self.bitrate

      get_media()._set_test_details(
        size_encoded = encsize,
        bitrate_actual = "{:-.2f}".format(bitrate_actual),
        bitrate_gap = "{:.2%}".format(bitrate_gap))

      # acceptable bitrate within 10% of bitrate
      assert(bitrate_gap <= 0.10)

    elif "vbr" == self.rcmode:
      encsize = os.path.getsize(self.encoded)
      bitrate_actual = encsize * 8 * self.fps / 1024.0 / self.frames

      get_media()._set_test_details(
        size_encoded = encsize,
        bitrate_actual = "{:-.2f}".format(bitrate_actual))

      # acceptable bitrate within 25% of minrate and 10% of maxrate
      assert(self.minrate * 0.75 <= bitrate_actual <= self.maxrate * 1.10)
