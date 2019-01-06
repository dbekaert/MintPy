#!/usr/bin/env python3

import os
import sys
import argparse
import numpy as np
from lxml import etree
import matplotlib as mpl
import matplotlib.pyplot as plt
from pykml.factory import KML_ElementMaker as KML
from pysar.objects import timeseries
from pysar.utils import readfile, plot


def create_parser():

    parser = argparse.ArgumentParser(description='Generare Google Earth Compatible KML for offline timeseries analysis',
                                     formatter_class=argparse.RawTextHelpFormatter)

    args = parser.add_argument_group('Input File', 'File/Dataset to display')

    args.add_argument('ts_file', metavar='timeseries_file', help='Timeseries file to generate KML for')
    args.add_argument('--vel', dest='vel_file', metavar='velocity_file', help='Velocity file')
    args.add_argument('-v','--vlim', dest='vlim', nargs=2, metavar=('VMIN', 'VMAX'), type=float,
                      help='Display limits for matrix plotting.')
    args.add_argument('-c', '--colormap', dest='colormap',
                     help='colormap used for display, i.e. jet, RdBu, hsv, jet_r, temperature, viridis,  etc.\n'
                          'colormaps in Matplotlib - http://matplotlib.org/users/colormaps.html\n'
                          'colormaps in GMT - http://soliton.vm.bytemark.co.uk/pub/cpt-city/')
    return parser


def cmd_line_parse(iargs=None):

    parser = create_parser()
    inps = parser.parse_args(args=iargs)

    return inps


def get_lat_lon(meta, mask=None):
    """extract lat/lon info of all grids into 2D matrix
    Parameters: meta : dict, including X/Y_FIRST/STEP and LENGTH/WIDTH info
    Returns:    lats : 2D np.array for latitude  in size of (length, width)
                lons : 2D np.array for longitude in size of (length, width)
    """
    # generate 2D matrix for lat/lon
    lat_num = int(meta['LENGTH'])
    lon_num = int(meta['WIDTH'])
    lat0 = float(meta['Y_FIRST'])
    lon0 = float(meta['X_FIRST'])
    lat_step = float(meta['Y_STEP'])
    lon_step = float(meta['X_STEP'])
    lat1 = lat0 + lat_step * lat_num
    lon1 = lon0 + lon_step * lon_num
    lats, lons = np.mgrid[lat0:lat1:lat_num*1j,
                          lon0:lon1:lon_num*1j]
    return lats, lons


def main(iargs=None):

    inps = cmd_line_parse(iargs)

    out_name_base = plot.auto_figure_title(inps.ts_file, inps_dict=vars(inps))

    cbar_png_file = '{}_cbar.png'.format(out_name_base)
    dygraph_file = "dygraph-combined.js"
    dot_file = "shaded_dot.png"
    kml_file = '{}.kml'.format(out_name_base)
    kmz_file = '{}.kmz'.format(out_name_base)

    ts_file = inps.ts_file
    vel_file = inps.vel_file

    ts_obj = timeseries(ts_file)
    ts_obj.open()


    ## read data

    # Date
    dates = np.array(ts_obj.times)  # 1D np.array of dates in datetime.datetime object in size of [num_date,]
    dates = list(map(lambda d: d.strftime("%Y-%m-%d"), dates))


    # Velocity / time-series
    vel = readfile.read(vel_file)[0]
    mask = ~np.isnan(vel)                   # matrix indicating valid pixels (True for valid, False for invalid)
    vel = readfile.read(vel_file)[0][mask]*100  # 1D np.array of velocity   in np.float32 in size of [num_pixel,] in meter/year
    ts = readfile.read(ts_file)[0][:, mask]*100     # 2D np.array of time-sries in np.float32 in size of [num_date, num_pixel] in meter

    ts_min = np.min(ts)
    ts_max = np.max(ts)


    # Set min/max velocity for colormap
    if inps.vlim is None:
        min_vel = min(vel)
        max_vel = max(vel)
    else:
        min_vel = inps.vlim[0]
        max_vel = inps.vlim[1]

    if inps.colormap is None:
        cmap = "jet"
    else:
        cmap = inps.colormap


    # Spatial coordinates
    lats = get_lat_lon(ts_obj.metadata)[0][mask]  # 1D np.array of latitude  in np.float32 in size of [num_pixel,] in degree
    lons = get_lat_lon(ts_obj.metadata)[1][mask]  # 1D np.array of longitude in np.float32 in size of [num_pixel,] in degree
    coords = list(zip(lats, lons))


    # Create and save colorbar image
    pc = plt.figure(figsize=(8, 1))
    cax = pc.add_subplot(111)
    norm = mpl.colors.Normalize(vmin=min_vel, vmax=max_vel)  # normalize velocity colors between 0.0 and 1.0
    cbar = mpl.colorbar.ColorbarBase(cax, cmap=cmap, norm=norm, orientation='horizontal')
    cbar.set_label('{} [{}]'.format("Velocity", "cm"))
    cbar.update_ticks()
    pc.patch.set_facecolor('white')
    pc.patch.set_alpha(0.7)
    print('writing ' + cbar_png_file)
    pc.savefig(cbar_png_file, bbox_inches='tight', facecolor=pc.get_facecolor(), dpi=300)


    # Create KML Document
    kml = KML.kml()
    kml_document = KML.Document()

    # Create Screen Overlay element for colorbar
    legend_overlay = KML.ScreenOverlay(
        KML.Icon(
            KML.href(cbar_png_file),
            KML.viewBoundScale(0.75)
        ),
        KML.overlayXY(x="0", y="0", xunits="pixels", yunits="insetPixels"),
        KML.screenXY(x="0", y="0", xunits="pixels", yunits="insetPixels"),
        KML.size(x="350", y="0", xunits="pixel", yunits="pixel"),
        KML.rotation(0),
        KML.visibility(1),
        KML.open(0)
    )

    kml_document.append(legend_overlay)


    print("Creating KML file. This may take some time.")
    for i in range(0, len(coords), 10):
        lat = coords[i][0]
        lon = coords[i][1]
        v = vel[i]

        colormap = mpl.cm.get_cmap(cmap)                    # set colormap
        rgba = colormap(norm(v))                            # get rgba color components for point velocity
        hex = mpl.colors.to_hex([rgba[3], rgba[2],
                                 rgba[1], rgba[0]],
                                keep_alpha=True)[1:]    # convert rgba to hex components reversed for kml color specification

        # Create KML icon style element
        style = KML.Style(
                    KML.IconStyle(
                        KML.color(hex),
                        KML.scale(0.5),
                        KML.Icon(
                            KML.href(dot_file)
                        )
                    )
                )

        # Create KML point element
        point = KML.Point(
                    KML.coordinates("{},{}".format(lon, lat))
                )

        # Javascript to embed inside the description
        js_data_string = "< ![CDATA[\n" \
                            "<script type='text/javascript' src='"+dygraph_file+"'></script>\n" \
                            "<div id='graphdiv'> </div>\n" \
                            "<script type='text/javascript'>\n" \
                                "g = new Dygraph( document.getElementById('graphdiv'),\n" \
                                "\"Date, Displacement\\n\" + \n"

        for j in range(len(dates)):
            date = dates[j]
            displacement = ts[j][i]

            date_displacement_string = "\"{}, {}\\n\" + \n".format(date, displacement)  # append the date/displacement data

            js_data_string += date_displacement_string

        js_data_string +=       "\"\",\n" \
                                "{" \
                                    "valueRange: ["+str(ts_min)+","+str(ts_max)+"]," \
                                    "ylabel: '[cm]'," \
                                "});" \
                              "</script>" \
                          "]]>"

        # Create KML description element
        description = KML.description(js_data_string)

        # Crate KML Placemark element to hold style, description, and point elements
        placemark = KML.Placemark(style, description, point)

        # Append each placemark element to the KML document object
        kml_document.append(placemark)

    kml.append(kml_document)


    # Copy shaded_dot file
    dot_path = os.path.dirname(__file__) + "/utils/"+dot_file
    cmdDot = "cp {} {}".format(dot_path, dot_file)
    print("copying {} for reference.\n".format(dot_file))
    os.system(cmdDot)

    # Copt dygraph-combined.js file
    dygraph_path = os.path.dirname(__file__) + "/utils/" + dygraph_file
    cmdDygraph = "cp {} {}".format(dygraph_path, dygraph_file)
    print("copying {} for reference\n".format(dygraph_file))
    os.system(cmdDygraph)

    # Write KML file
    print('writing ' + kml_file)
    with open(kml_file, 'w') as f:
        f.write(etree.tostring(kml, pretty_print=True).decode('utf-8'))

    # Generate KMZ file
    cmdKMZ = 'zip {} {} {} {} {}'.format(kmz_file, kml_file, cbar_png_file, dygraph_file, dot_file)
    print('writing {}\n{}'.format(kmz_file, cmdKMZ))
    os.system(cmdKMZ)

    cmdClean = 'rm {} {} {} {}'.format(kml_file, cbar_png_file, dygraph_file, dot_file)
    print(cmdClean)
    os.system(cmdClean)


######################################################################################
if __name__ == '__main__':
    main()
