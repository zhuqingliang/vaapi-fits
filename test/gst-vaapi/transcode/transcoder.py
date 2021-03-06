###
### Copyright (C) 2018-2019 Intel Corporation
###
### SPDX-License-Identifier: BSD-3-Clause
###

from ....lib import *
from ..util import *
import os

@slash.requires(have_gst)
@slash.requires(*have_gst_element("vaapi"))
@slash.requires(*have_gst_element("checksumsink2"))
@platform_tags(ALL_PLATFORMS)
class TranscoderTest(slash.Test):
  requirements = dict(
    decode = {
      "avc" : dict(
        sw = (ALL_PLATFORMS, have_gst_element("avdec_h264"), "h264parse ! avdec_h264"),
        hw = (AVC_DECODE_PLATFORMS, have_gst_element("vaapih264dec"), "h264parse ! vaapih264dec"),
      ),
      "hevc-8" : dict(
        sw = (ALL_PLATFORMS, have_gst_element("avdec_h265"), "h265parse ! avdec_h265"),
        hw = (HEVC_DECODE_8BIT_PLATFORMS, have_gst_element("vaapih265dec"), "h265parse ! vaapih265dec"),
      ),
      "mpeg2" : dict(
        sw = (ALL_PLATFORMS, have_gst_element("avdec_mpeg2video"), "mpegvideoparse ! avdec_mpeg2video"),
        hw = (MPEG2_DECODE_PLATFORMS, have_gst_element("vaapimpeg2dec"), "mpegvideoparse ! vaapimpeg2dec"),
      ),
      "mjpeg" : dict(
        sw = (ALL_PLATFORMS, have_gst_element("jpegdec"), "jpegparse ! jpegdec"),
        hw = (JPEG_DECODE_PLATFORMS, have_gst_element("vaapijpegdec"), "jpegparse ! vaapijpegdec"),
      ),
      "vc1" : dict(
        sw = (
          ALL_PLATFORMS, have_gst_element("avdec_vc1"),
          "'video/x-wmv,profile=(string)advanced'"
          ",width={width},height={height},framerate=14/1 ! avdec_vc1"
        ),
        hw = (
          VC1_DECODE_PLATFORMS, have_gst_element("vaapivc1dec"),
          "'video/x-wmv,profile=(string)advanced'"
          ",width={width},height={height},framerate=14/1 ! vaapivc1dec"
        ),
      ),
    },
    encode = {
      "avc" : dict(
        sw = (ALL_PLATFORMS, have_gst_element("x264enc"), "x264enc ! video/x-h264,profile=main ! h264parse"),
        hw = (AVC_ENCODE_PLATFORMS, have_gst_element("vaapih264enc"), "vaapih264enc ! video/x-h264,profile=main ! h264parse"),
      ),
      "hevc-8" : dict(
        sw = (ALL_PLATFORMS, have_gst_element("x265enc"), "x265enc ! video/x-h265,profile=main ! h265parse"),
        hw = (HEVC_ENCODE_8BIT_PLATFORMS, have_gst_element("vaapih265enc"), "vaapih265enc ! video/x-h265,profile=main ! h265parse"),
      ),
      "mpeg2" : dict(
        sw = (ALL_PLATFORMS, have_gst_element("avenc_mpeg2video"), "avenc_mpeg2video ! mpegvideoparse"),
        hw = (MPEG2_ENCODE_PLATFORMS, have_gst_element("vaapimpeg2enc"), "vaapimpeg2enc ! mpegvideoparse"),
      ),
      "mjpeg" : dict(
        sw = (ALL_PLATFORMS, have_gst_element("jpegenc"), "jpegenc ! jpegparse"),
        hw = (JPEG_ENCODE_PLATFORMS, have_gst_element("vaapijpegenc"), "vaapijpegenc ! jpegparse"),
      ),
    },
    vpp = {
      "scale" : dict(
        sw = (ALL_PLATFORMS, have_gst_element("videoscale"), "videoscale ! video/x-raw,width={width},height={height}"),
        hw = (VPP_PLATFORMS, have_gst_element("vaapipostproc"), "vaapipostproc ! video/x-raw,width={width},height={height}"),
      ),
    },
  )

  # hevc implies hevc 8 bit
  requirements["encode"]["hevc"] = requirements["encode"]["hevc-8"]
  requirements["decode"]["hevc"] = requirements["decode"]["hevc-8"]

  def before(self):
    self.refctx = []

  def get_requirements_data(self, ttype, codec, mode):
    return  self.requirements[ttype].get(
      codec, {}).get(
        mode, ([], (False, "{}:{}:{}".format(ttype, codec, mode)), None))

  def get_decoder(self, codec, mode):
    _, _, decoder = self.get_requirements_data("decode", codec, mode)
    assert decoder is not None, "failed to find a suitable decoder: {}:{}".format(codec, mode)
    return decoder.format(**vars(self))

  def get_encoder(self, codec, mode):
    _, _, encoder = self.get_requirements_data("encode", codec, mode)
    assert encoder is not None, "failed to find a suitable encoder: {}:{}".format(codec, mode)
    return encoder.format(**vars(self))

  def get_vpp_scale(self, width, height, mode):
    if width is None and height is None:
      return None
    _, _, scale = self.get_requirements_data("vpp", "scale", mode)
    assert scale is not None, "failed to find a suitable vpp scaler: {}".format(mode)
    return scale.format(width = width or self.width, height = height or self.height)

  def get_file_ext(self, codec):
    return {
      "avc"     : "h264",
      "hevc"    : "h265",
      "hevc-8"  : "h265",
      "mpeg2"   : "m2v",
      "mjpeg"   : "mjpeg",
    }.get(codec, "???")

  def validate_spec(self):
    from slash.utils.pattern_matching import Matcher

    assert len(self.outputs), "Invalid test case specification, outputs data empty"
    assert self.mode in ["sw", "hw"], "Invalid test case specification as mode type not valid"

    # generate platform list based on test runtime parameters
    iplats, ireq, _ =  self.get_requirements_data("decode", self.codec, self.mode)
    platforms = set(iplats)
    requires = [ireq,]

    for output in self.outputs:
      codec = output["codec"]
      mode  = output["mode"]
      assert mode in ["sw", "hw"], "Invalid test case specification as output mode type not valid"
      oplats, oreq, _ = self.get_requirements_data("encode", codec, mode)
      platforms &= set(oplats)
      requires.append(oreq)

      if output.get("width", None) is not None or output.get("height", None) is not None:
        oplats, oreq, _ = self.get_requirements_data("vpp", "scale", mode)
        platforms &= set(oplats)
        requires.append(oreq)

    # create matchers based on command-line filters
    matchers = [Matcher(s) for s in slash.config.root.run.filter_strings]

    # check if user supplied any platform tag on command line
    pmatch = any(map(lambda p: any([m.matches(p) for m in matchers]), ALL_PLATFORMS))

    # if user supplied a platform tag, check if this test can support it via the
    # test param-based required platforms
    if pmatch and not any(map(lambda p: any([m.matches(p) for m in matchers]), platforms)):
      slash.skip_test("unsupported platform")

    # check required
    if not all([t for t,m in requires]):
      slash.skip_test(
        "One or more software requirements not met: {}".format(
          str([m for t,m in requires if not t])))

  def gen_input_opts(self):
    opts = "filesrc location={source}"
    opts += " ! " + self.get_decoder(self.codec, self.mode)
    return opts.format(**vars(self))

  def gen_output_opts(self):
    self.goutputs = dict()
    opts = "! tee name=transcoder"

    for n, output in enumerate(self.outputs):
      codec = output["codec"]
      mode  = output["mode"]
      encoder = self.get_encoder(codec, mode)
      ext = self.get_file_ext(codec)

      vppscale = self.get_vpp_scale(
        output.get("width", None), output.get("height", None), mode)

      for channel in xrange(output.get("channels", 1)):
        ofile = get_media()._test_artifact(
          "{}_{}_{}.{}".format(self.case, n, channel, ext))
        self.goutputs.setdefault(n, list()).append(ofile)

        opts += " ! queue"
        if vppscale is not None:
          opts += " ! {}".format(vppscale)
        opts += " ! {}".format(encoder)
        opts += " ! filesink location={} transcoder.".format(ofile)

    # dump decoded source to yuv for reference comparison
    self.srcyuv = get_media()._test_artifact(
      "src_{case}.yuv".format(**vars(self)))
    opts += " ! queue ! videoconvert ! video/x-raw,format=I420"
    opts += " ! checksumsink2 file-checksum=false qos=false"
    opts += " frame-checksum=false plane-checksum=false dump-output=true"
    opts += " dump-location={srcyuv}"

    return opts.format(**vars(self))

  def transcode(self):
    self.validate_spec()
    iopts = self.gen_input_opts()
    oopts = self.gen_output_opts()

    get_media().test_call_timeout = vars(self).get("call_timeout", 0)

    call("gst-launch-1.0 -vf {} {}".format(iopts, oopts))

    for n, output in enumerate(self.outputs):
      for channel in xrange(output.get("channels", 1)):
        encoded = self.goutputs[n][channel]
        yuv = get_media()._test_artifact(
          "{}_{}_{}.yuv".format(self.case, n, channel))
        vppscale = self.get_vpp_scale(self.width, self.height, "hw")
        call(
          "gst-launch-1.0 -vf filesrc location={}"
          " ! {} ! {}"
          " ! videoconvert ! video/x-raw,format=I420"
          " ! checksumsink2 file-checksum=false qos=false"
          " frame-checksum=false plane-checksum=false dump-output=true"
          " dump-location={}".format(
            encoded, self.get_decoder(output["codec"], "hw"), vppscale, yuv))
        self.check_metrics(yuv, refctx = [(n, channel)])
        get_media()._purge_test_artifact(yuv)

  def check_metrics(self, yuv, refctx):
    get_media().baseline.check_psnr(
      psnr = calculate_psnr(
        self.srcyuv, yuv,
        self.width, self.height,
        self.frames),
      context = self.refctx + refctx,
    )
