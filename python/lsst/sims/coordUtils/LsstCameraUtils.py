from __future__ import division
import numpy as np
import lsst.afw.geom as afwGeom
from lsst.afw.cameraGeom import PUPIL, PIXELS, WAVEFRONT
from lsst.sims.coordUtils import pupilCoordsFromPixelCoords
from lsst.sims.utils import _pupilCoordsFromRaDec
from lsst.sims.coordUtils import getCornerPixels
from lsst.sims.utils.CodeUtilities import _validate_inputs
from lsst.obs.lsstSim import LsstSimMapper

__all__ = ["chipNameFromPupilCoordsLSST",
           "_chipNameFromRaDecLSST"]

_lsst_camera = LsstSimMapper().camera

_lsst_pupil_coord_map = None

def _build_lsst_pupil_coord_map():
    """
    This method populates the global variable _lsst_pupil_coord_map
    _lsst_pupil_coord_map['name'] contains a list of the names of each chip in the lsst camera
    _lsst_pupil_coord_map['xx'] contains the x pupil coordinate of the center of each chip
    _lsst_pupil_coord_map['yy'] contains the y pupil coordinate of the center of each chip
    _lsst_pupil_coord_map['dp'] contains the radius (in pupil coordinates) of the circle containing each chip
    """
    global _lsst_camera
    global _lsst_pupil_coord_map
    if _lsst_pupil_coord_map is not None:
        raise RuntimeError("Calling _build_pupil_coord_map(), "
                           "but it is already built.")

    name_list = []
    x_pix_list = []
    y_pix_list = []
    n_chips = 0
    for chip in _lsst_camera:
        chip_name = chip.getName()
        n_chips += 1
        corner_list = getCornerPixels(chip_name, _lsst_camera)
        for corner in corner_list:
            x_pix_list.append(corner[0])
            y_pix_list.append(corner[1])
            name_list.append(chip_name)

    x_pix_list = np.array(x_pix_list)
    y_pix_list = np.array(y_pix_list)

    x_pup_list, y_pup_list = pupilCoordsFromPixelCoords(x_pix_list,
                                                        y_pix_list,
                                                        name_list,
                                                        camera=_lsst_camera)
    center_x = np.zeros(n_chips, dtype=float)
    center_y = np.zeros(n_chips, dtype=float)
    extent = np.zeros(n_chips, dtype=float)
    final_name = []
    for ix_ct in range(n_chips):
        ix = ix_ct*4
        chip_name = name_list[ix]
        xx = 0.25*(x_pup_list[ix] + x_pup_list[ix+1]
                   + x_pup_list[ix+2] + x_pup_list[ix+3])

        yy = 0.25*(y_pup_list[ix] + y_pup_list[ix+1]
                   + y_pup_list[ix+2] + y_pup_list[ix+3])

        dx = 0.25*np.array([np.sqrt(np.power(xx-x_pup_list[ix+ii], 2)
                                    + np.power(yy-y_pup_list[ix+ii], 2)) for ii in range(4)]).sum()

        center_x[ix_ct] = xx
        center_y[ix_ct] = yy
        extent[ix_ct] = dx
        final_name.append(chip_name)

    final_name = np.array(final_name)

    _lsst_pupil_coord_map = {}
    _lsst_pupil_coord_map['name'] = final_name
    _lsst_pupil_coord_map['xx'] = center_x
    _lsst_pupil_coord_map['yy'] = center_y
    _lsst_pupil_coord_map['dp'] = extent


def _findDetectorsListLSST(cameraPointList, detectorList, allow_multiple_chips=False):
    """!Find the detectors that cover a list of points specified by x and y coordinates in any system

    This is based one afw.camerGeom.camera.findDetectorsList.  It has been optimized for the LSST
    camera in the following way:

        - it accepts a limited list of detectors to check in advance (this list should be
          constructed by comparing the pupil coordinates in question and comparing to the
          pupil coordinates of the center of each detector)

       - it will stop looping through detectors one it has found one that is correct (the LSST
         camera does not allow an object to fall on more than one detector)

    @param[in] cameraPointList  a list of cameraPoints in PUPIL coordinates

    @param[in] detecorList is a list of lists.  Each row contains the detectors that should be searched
    for the correspdonding cameraPoint

    @param [in] allow_multiple_chips is a boolean (default False) indicating whether or not
    this method will allow objects to be visible on more than one chip.  If it is 'False'
    and an object appears on more than one chip, only the first chip will appear in the list of
    chipNames but NO WARNING WILL BE EMITTED.  If it is 'True' and an object falls on more than one
    chip, a list of chipNames will appear for that object.

    @return outputNameList is a numpy array of the names of the detectors
    """

    global _lsst_camera

    #transform the points to the native coordinate system
    nativePointList = _lsst_camera._transformSingleSysArray(cameraPointList, PUPIL, _lsst_camera._nativeCameraSys)

    outputNameList = [None]*len(cameraPointList)
    chip_has_found = np.array([-1]*len(cameraPointList))
    checked_detectors = []

    could_be_multiple = [False]*len(cameraPointList)
    if allow_multiple_chips:
        for ipt in range(len(cameraPointList)):
            for det in detectorList[ipt]:
                if det.getType() == WAVEFRONT:
                    could_be_multiple[ipt] = True

    for ipt, nativePoint in enumerate(nativePointList):
        if outputNameList[ipt] is None:
            for detector in detectorList[ipt]:
                if detector.getName() not in checked_detectors:
                    checked_detectors.append(detector.getName())
                    unfound_pts = np.where(chip_has_found<0)[0]
                    if len(unfound_pts) == 0:
                        for ix, name in enumerate(outputNameList):
                            if isinstance(name, list):
                                outputNameList[ix] = str(name)
                        return np.array(outputNameList)
                    valid_pt_dexes = np.array([ii for ii in unfound_pts if detector in detectorList[ii]])
                    if len(valid_pt_dexes)>0:
                        valid_pt_list = [nativePointList[ii] for ii in valid_pt_dexes]
                        coordMap = detector.getTransformMap()
                        cameraSys = detector.makeCameraSys(PIXELS)
                        detectorPointList = coordMap.transform(valid_pt_list, _lsst_camera._nativeCameraSys, cameraSys)
                        box = afwGeom.Box2D(detector.getBBox())
                        for ix, pt in zip(valid_pt_dexes, detectorPointList):
                            if box.contains(pt):
                                if not could_be_multiple[ix]:
                                    outputNameList[ix] = detector.getName()
                                    chip_has_found[ix] = 1
                                else:
                                    if outputNameList[ix] is None:
                                        outputNameList[ix] = detector.getName()
                                    elif isinstance(outputNameList[ix], list):
                                        outputNameList[ix].append(detector.getName())
                                    else:
                                        outputNameList[ix] = [outputNameList[ix], detector.getName()]

    for ix, name in enumerate(outputNameList):
        if isinstance(name, list):
            outputNameList[ix] = str(name)

    return np.array(outputNameList)



def chipNameFromPupilCoordsLSST(xPupil, yPupil, allow_multiple_chips=False):
    """
    Return the names of LSST detectors that see the object specified by
    either (xPupil, yPupil).

    @param [in] xPupil is the x pupil coordinate in radians.
    Must be a numpy array.

    @param [in] yPupil is the y pupil coordinate in radians.
    Must be a numpy array.

    @param [in] allow_multiple_chips is a boolean (default False) indicating whether or not
    this method will allow objects to be visible on more than one chip.  If it is 'False'
    and an object appears on more than one chip, only the first chip will appear in the list of
    chipNames and warning will be emitted.  If it is 'True' and an object falls on more than one
    chip, a list of chipNames will appear for that object.

    @param [out] a numpy array of chip names

    """

    global _lsst_pupil_coord_map
    if _lsst_pupil_coord_map is None:
        _build_lsst_pupil_coord_map()

    are_arrays = _validate_inputs([xPupil, yPupil], ['xPupil', 'yPupil'], "chipNameFromPupilCoordsLSST")

    if not are_arrays:
        raise RuntimeError("Pupil coordinates passed to chipNameFromPupilCoordsLSST must be in numpy arrays")

    cameraPointList = [afwGeom.Point2D(x, y) for x, y in zip(xPupil, yPupil)]

    valid_detectors = []
    for xx, yy in zip(xPupil, yPupil):
        possible_dexes = np.where(np.sqrt(np.power(xx-_lsst_pupil_coord_map['xx'],2)
                                          + np.power(yy-_lsst_pupil_coord_map['yy'],2))/_lsst_pupil_coord_map['dp']<1.1)

        local_valid = [_lsst_camera[_lsst_pupil_coord_map['name'][ii]] for ii in possible_dexes[0]]
        valid_detectors.append(local_valid)

    nameList = _findDetectorsListLSST(cameraPointList, valid_detectors, allow_multiple_chips=allow_multiple_chips)

    return nameList


def _chipNameFromRaDecLSST(ra, dec, obs_metadata=None, epoch=2000.0, allow_multiple_chips=False):
    """
    Return the names of detectors on the LSST camera that see the object specified by
    (RA, Dec) in radians.

    @param [in] ra in radians (a numpy array or a float).
    In the International Celestial Reference System.

    @param [in] dec in radians (a numpy array or a float).
    In the International Celestial Reference System.

    @param [in] obs_metadata is an ObservationMetaData characterizing the telescope pointing

    @param [in] epoch is the epoch in Julian years of the equinox against which RA and Dec are
    measured.  Default is 2000.

    @param [in] allow_multiple_chips is a boolean (default False) indicating whether or not
    this method will allow objects to be visible on more than one chip.  If it is 'False'
    and an object appears on more than one chip, only the first chip will appear in the list of
    chipNames but NO WARNING WILL BE EMITTED.  If it is 'True' and an object falls on more than one
    chip, a list of chipNames will appear for that object.

    @param [out] a numpy array of chip names
    """

    _validate_inputs([ra, dec], ['ra', 'dec'], "chipNameFromRaDecLSST")

    if epoch is None:
        raise RuntimeError("You need to pass an epoch into chipName")

    if obs_metadata is None:
        raise RuntimeError("You need to pass an ObservationMetaData into chipName")

    if obs_metadata.mjd is None:
        raise RuntimeError("You need to pass an ObservationMetaData with an mjd into chipName")

    if obs_metadata.rotSkyPos is None:
        raise RuntimeError("You need to pass an ObservationMetaData with a rotSkyPos into chipName")

    xp, yp = _pupilCoordsFromRaDec(ra, dec, obs_metadata=obs_metadata, epoch=epoch)
    return chipNameFromPupilCoordsLSST(xp, yp, allow_multiple_chips=allow_multiple_chips)
