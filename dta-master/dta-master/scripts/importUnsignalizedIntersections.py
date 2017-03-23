__copyright__   = "Copyright 2011 SFCTA"
__license__     = """
    This file is part of DTA.

    DTA is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    DTA is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with DTA.  If not, see <http://www.gnu.org/licenses/>.
"""


import dta
from itertools import izip
import os
import re
import shapefile
import sys 


USAGE = r"""

 python importUnsignalizedIntersections.py dynameq_net_dir dynameq_net_prefix stop_signs.shp
 
 e.g.
 
 python importUnsignalizedIntersections.py . sf Q:\GIS\Road\StopSigns\allway_stops.shp  Q:\GIS\CityGIS\TrafficControl\StopSigns\stops_signs.shp 
 
 This script reads all unsignalized intersections from shapefile and updates the priorities of the matching node accordingly.
  
 The script writes a new dynameq network that includes the new priorities as sf_stops_*.dqt
 """

def readStopSignShapefile(shapefilename):
    """
    Reads the stop sign shapefile and returns the following:
    
    { cnn -> [ record1_dict, record2_dict, ... ] }
    
    Where *record_dict* includes all the fields from the shapefile, plus `COORDS` which maps to the coordinate tuple.
    """
    sf      = shapefile.Reader(shapefilename)
    fields  = [field[0] for field in sf.fields[1:]]
    count   = 0
    nocnn_id= 1
    
    # what we're returning
    cnn_to_recordlist = {}
    for sr in sf.shapeRecords():
        
        # name the records
        sr_record_dict = dict(izip(fields, sr.record))
        
        # we expect these shapes to have one point
        if len(sr.shape.points) != 1: continue

        point = sr.shape.points[0]
        cnn   = sr_record_dict['CNN']
        if cnn == 0:
            cnn = "nocnn_%d" % nocnn_id
            nocnn_id += 1
        # hack - consolidated cnn
        elif cnn == 26099000:
            cnn = 26101000
        elif cnn == 22457000:
            cnn = 22456000
        
        # add the point
        sr_record_dict['COORDS'] = point
        if cnn not in cnn_to_recordlist:
            cnn_to_recordlist[cnn] = []
        cnn_to_recordlist[cnn].append(sr_record_dict)
        count += 1

    dta.DtaLogger.info("Read %d unique nodes and %d stop signs from %s" % (len(cnn_to_recordlist), count, shapefilename))
    return cnn_to_recordlist
    
def cleanStreetName(streetName):
    """
    Given a streetname, this function attempts to make it uniform with the San Francisco DTA Network streetnames.
    """

    # these will be treated as regexes so you can specify ^ for the beginning of the string
    # $ for the end, wild chars, etc
    corrections = {"TWELFTH":"12TH", 
                   "ELEVENTH":"11TH",
                   "TENTH":"10TH",
                   "NINTH":"9TH",
                   "EIGHTH":"8TH",
                   "SEVENTH":"7TH",
                   "SIXTH":"6TH",
                   "FIFTH":"5TH",
                   "FOURTH":"4TH",
                   "THIRD":"3RD",
                   "SECOND":"2ND",
                   "FIRST":"1ST",
                   "3RDREET":"3RD",
                   "3RD #3":"3RD",
                   "BAYSHORE #3":"BAYSHORE",
                   "09TH":"9TH",
                   "08TH":"8TH",
                   "07TH":"7TH",
                   "06TH":"6TH",
                   "05TH":"5TH",
                   "04TH":"4TH",
                   "03RD":"3RD",
                   "02ND":"2ND",
                   "01ST":"1ST",
                   "ARMY":"CESAR CHAVEZ",
                   "DEL SUR":"DELSUR",
                   "EMBARCADERO/KING":"THE EMBARCADERO",
                   "GREAT HIGHWAY":"GREAT HWY",
                   "O'FARRELL":"O FARRELL",
                   "MARTIN L(UTHER)? KING":"MLK",
                   "MCALLISTER":"MC ALLISTER",
                   "MCKINNON":"MC KINNON",
                   "MIDDLEPOINT":"MIDDLE POINT",
                   "MT VERNON":"MOUNT VERNON",
                   "^ST ":"SAINT ",            
                   "VAN NESSNUE":"VAN NESS",                   
                   "WEST GATE":"WESTGATE",
                   }

    cleaned_name = streetName.strip()
    for wrongName, rightName in corrections.items():
        cleaned_name = re.sub(wrongName, rightName, cleaned_name)
    return cleaned_name

def checkStreetnameConsistency(dta_node_id, dta_streets, stopsign_streets, stopsign_x_streets):
    """
    Verifies that the stopsign streets and the stopsign_x_streets are subsets of dta_streets.
    Warns about violations.
    
    *dta_node_id* is an integer, just used for logging.  All three  remaining inputs are lists of strings.
    """
    # these are what we're checking
    # check once, and "stopsign street" overrides "stopsign X street"
    checkname_to_checktype = {}
    for stopsign_x_street in stopsign_x_streets:
        checkname_to_checktype[cleanStreetName(stopsign_x_street)] = "stopsign X street"

    for stopsign_street in stopsign_streets:
        checkname_to_checktype[cleanStreetName(stopsign_street)] = "stopsign street"
    
    # actually check them now
    for checkname,checktype in checkname_to_checktype.iteritems():

        found = False
        for dta_street in dta_streets:
            # if any of the dta_streets start with it, coo
            if dta_street.startswith(checkname):
                found = True
                break
            
        if not found:    
            dta.DtaLogger.warn("Streetname consistency check: node %d doesn't have %s [%s]  (Searched %s)" % 
                               (dta_node_id, checktype, checkname, str(dta_streets)))


#: this_is_main                
if __name__ == "__main__":

    if len(sys.argv) != 4:
        print USAGE
        sys.exit(2)

    INPUT_DYNAMEQ_NET_DIR         = sys.argv[1]
    INPUT_DYNAMEQ_NET_PREFIX      = sys.argv[2]
    STOP_SHAPEFILE                = sys.argv[3]
    
    # The SanFrancisco network will use feet for vehicle lengths and coordinates, and miles for link lengths
    dta.VehicleType.LENGTH_UNITS= "feet"
    dta.Node.COORDINATE_UNITS   = "feet"
    dta.RoadLink.LENGTH_UNITS   = "miles"

    dta.setupLogging("importUnsignalizedIntersections.INFO.log", "importUnsignalizedIntersections.DEBUG.log", logToConsole=True)

    scenario = dta.DynameqScenario()
    scenario.read(INPUT_DYNAMEQ_NET_DIR, INPUT_DYNAMEQ_NET_PREFIX) 
    net = dta.DynameqNetwork(scenario)
    net.read(INPUT_DYNAMEQ_NET_DIR, INPUT_DYNAMEQ_NET_PREFIX)

    cnn_to_recordlist = readStopSignShapefile(STOP_SHAPEFILE)
    
    count_notmapped     = 0
    count_hassignal     = 0
    count_moreincoming  = 0
    count_allway        = 0
    count_twoway        = 0 # no custom
    count_twoway_custom = 0
    count_allway_fromtwo= 0 # use this?
    
    # the cnn is unique per intersection so loop through each intersection with stop signs
    for cnn, stopsignlist in cnn_to_recordlist.iteritems():
        
        # these are the streets for the stop signs
        stopsign_streets   = []
        stopsign_x_streets = []
        # and the dirs
        stopsign_dirs      = []
        for stopsign in stopsignlist:
            if stopsign['STREET'] not in stopsign_streets:
                stopsign_streets.append(stopsign['STREET'])
            if stopsign['X_STREET'] not in stopsign_x_streets:
                stopsign_x_streets.append(stopsign['X_STREET'])
            stopsign_dirs.append(stopsign['ST_FACING'])

        # find the nearest node to this                
        (min_dist, roadnode) = net.findNodeNearestCoords(stopsignlist[0]['COORDS'][0], stopsignlist[0]['COORDS'][1], quick_dist=100.0)
        
        if roadnode == None:
            dta.DtaLogger.warn("Could not find road node near %s and %s in the stop sign file" % (stopsignlist[0]['STREET'], stopsignlist[0]['X_STREET']))
            count_notmapped += 1
            continue

        dta.DtaLogger.debug("min_dist = %.3f roadnodeID=%d roadnode_streets=%s stopsign_streets=%s" % 
                            (min_dist, roadnode.getId(), str(roadnode.getStreetNames(incoming=True, outgoing=False)),
                             str(stopsign_streets)))

        # streetname checking; warn if stopsign_streets are not found in the roadnode_streets
        checkStreetnameConsistency(roadnode.getId(), roadnode.getStreetNames(incoming=True, outgoing=False),
                                   stopsign_streets, stopsign_x_streets)
                        
        # if the roadnode is already a signalized intersection, move on
        if roadnode.hasTimePlan():
            dta.DtaLogger.warn("Roadnode %d already has signal. Ignoring stop sign info." % roadnode.getId())
            count_hassignal += 1
            continue
        
        # warn when more stops than incoming links
        if len(stopsignlist) > roadnode.getNumIncomingLinks():
            dta.DtaLogger.warn("Roadnode %d missing incoming links?  More stop signs than incoming links" % roadnode.getId())
            count_moreincoming += 1 # not exclusive count!
            
        # if the number of incoming links == the number of stop signs
        # OR the number of stop signs is >=4
        # mark it an all way stop
        if  len(stopsignlist) >= roadnode.getNumIncomingLinks() or len(stopsignlist) >= 4:
            roadnode.setAllWayStopControl()
            count_allway += 1
            continue
        
        # two way stop -- assign custom priorities; incoming links with stops are lower priority than incoming links without stops
        inlink_stops   = []
        inlink_nostops = []     
        for inlink in roadnode.iterIncomingLinks():
            # by direction
            if inlink.getDirection() in stopsign_dirs:
                inlink_stops.append(inlink)
                continue
            # direction is there, name matches
            is_stop = False
            for stopsign in stopsignlist:
                if inlink.getLabel().startswith(stopsign['STREET']) and inlink.hasDirection(stopsign['ST_FACING']):
                    is_stop = True
                    break
            if is_stop:
                inlink_stops.append(inlink)
            else:
                inlink_nostops.append(inlink)                    
        
        dta.DtaLogger.debug("inlink_stops: "+str(inlink_stops))
        dta.DtaLogger.debug("inlink_nostops: "+str(inlink_nostops))
        
        # did we find all the stops?
        if len(inlink_stops) != len(stopsignlist):
            dta.DtaLogger.warn("RoadNode %d: stop links != stopsigns; links=[%s], stopsigns=[%s]" %
                                (roadnode.getId(), str(inlink_stops), str(stopsignlist)))

        # check if stop facilities > nostop facility
        min_stop_fac_num = 9999
        for inlink in inlink_stops:
            if min_stop_fac_num > inlink.getFacilityType(): min_stop_fac_num = inlink.getFacilityType()
        max_nostop_fac_num = -9999
        for inlink in inlink_nostops:
            if max_nostop_fac_num < inlink.getFacilityType(): max_nostop_fac_num = inlink.getFacilityType()
        dta.DtaLogger.debug("RoadNode %d: stop sign min facility num %d vs no-stop max facility num %d" % 
                            (roadnode.getId(), min_stop_fac_num, max_nostop_fac_num))
            
        # if so, we're done -- no need to customize
        if min_stop_fac_num > max_nostop_fac_num:
            roadnode.setTwoWayStopControl()
            count_twoway += 1
            continue
        
        # if not, we need to customize
        roadnode.setPriorityTemplateNone()
        count_twoway_custom += 1
        
        for inlink_stop in inlink_stops:
            for mov_stop in inlink_stop.iterOutgoingMovements():
                if mov_stop.isProhibitedToAllVehicleClassGroups(): continue
                
                # set the no-stop movements as higher priority
                for inlink_nostop in inlink_nostops:
                    for mov_nostop in inlink_nostop.iterOutgoingMovements():
                        if mov_nostop.isProhibitedToAllVehicleClassGroups(): continue
                        
                        # don't mention it if they're not in conflict anyway
                        if not mov_stop.isInConflict(mov_nostop): continue

                        # these are based on the (default) project settings
                        if mov_stop.isThruTurn():
                            critical_gap = 6.5
                        elif mov_stop.isLeftTurn():
                            critical_gap = 7.10
                        elif mov_stop.isRightTurn():
                            critical_gap = 6.2
                        else:
                            dta.DtaLogger.fatal("I don't recognize the turn type of the stop-sign controled movement %s" % move_stop)
                        mov_stop.addHigherPriorityMovement(mov_nostop, critical_gap=critical_gap, critical_wait=60)
                                   
    dta.DtaLogger.info("Read %d stop-sign intersections" % len(cnn_to_recordlist))
    dta.DtaLogger.info("  %-4d: Failed to map" % count_notmapped)
    dta.DtaLogger.info("  %-4d: Ignored because they're signalized" % count_hassignal)
    dta.DtaLogger.info("  %-4d: Setting as allway-stop (including %d questionable, with more stop signs than incoming links)" % (count_allway, count_moreincoming))
    dta.DtaLogger.info("  %-4d: Setting as allway-stop in lieu of custom priorities" % count_allway_fromtwo)
    dta.DtaLogger.info("  %-4d: Setting as twoway-stop without custom priorities" % count_twoway)
    dta.DtaLogger.info("  %-4d: Setting as twoway-stop with custom priorities" % count_twoway_custom)
    
    # Warn for any unsignalized intersection
    nothing_count = 0
    inconsistent_count = 0
    for roadnode in net.iterRoadNodes():
        # 1 or fewer incoming links: don't care
        if roadnode.getNumIncomingLinks() <= 1: continue
        
        # through movements don't conflict - ok fine
        thru_movements = []
        thru_conflict  = False
        for mov in roadnode.iterMovements():
            if mov.getTurnType() == dta.Movement.DIR_TH: thru_movements.append(mov)
        for mov1 in thru_movements:
            for mov2 in thru_movements:
                if mov1 == mov2: continue
                if mov1.isInConflict(mov2): 
                    thru_conflict = True
                    break
        if not thru_conflict: continue
        
        # signalized, with a time plan: ok
        if (roadnode.control == dta.RoadNode.CONTROL_TYPE_SIGNALIZED and 
            roadnode.priority == dta.RoadNode.PRIORITY_TEMPLATE_SIGNALIZED and 
            roadnode.hasTimePlan()):
            continue
        
        # stop control of some sort: ok
        if (roadnode.control == dta.RoadNode.CONTROL_TYPE_UNSIGNALIZED and 
            roadnode.priority != dta.RoadNode.PRIORITY_TEMPLATE_NONE): continue
        
        # it's either inconsistent or not set
        if (roadnode.control == dta.RoadNode.CONTROL_TYPE_UNSIGNALIZED and 
            roadnode.priority == dta.RoadNode.PRIORITY_TEMPLATE_NONE):
            dta.DtaLogger.warn("No stop control or signal   at node %8d: control=%d priority=%2d streets=%s" %
                               (roadnode.getId(), roadnode.control, roadnode.priority, 
                                roadnode.getStreetNames(incoming=True, outgoing=False)))
            nothing_count += 1

        else:
             dta.DtaLogger.warn("Inconsistent control/signal at node %8d: control=%d priority=%2d streets=%s" %
                               (roadnode.getId(), roadnode.control, roadnode.priority, 
                                roadnode.getStreetNames(incoming=True, outgoing=False)))
             inconsistent_count += 1
    dta.DtaLogger.info("Found %4d road nodes with no stop control or signals" % nothing_count)
    dta.DtaLogger.info("Found %4d road nodes with inconsistent stop control or signals" % inconsistent_count)
    
    net.write(".", "sf_stops")

    net.writeNodesToShp("sf_stops_nodes")
    net.writeLinksToShp("sf_stops_links")         
    

            
            

