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
import getopt
import os
import sys
import pdb

USAGE = r"""

 python createSFNetworkFromCubeNetwork.py  [-n output_nodes.shp] [-l output_links.shp]  sf_cube_net_file sf_cube_turnpen_file [cube_attach_shapefile]
 
 e.g.
 
 python createSFNetworkFromCubeNetwork.py -n sf_nodes.shp -l sf_links.shp Y:\dta\SanFrancisco\2010\SanFranciscoSubArea_2010.net Y:\dta\SanFrancisco\2010\network\turnspm.pen Q:\GIS\Road\SFCLINES\AttachToCube\stclines.shp
 
 This script reads the San Francisco Cube network and optionally the *cube_attach_shapefile*
 and converts it to a Dynameq network, writing it out to the current directory as sf_*.dqt.
 
  * The first arg is the San Francisco Cube network for conversion to a Dynameq DTA network
  * The second arg is the turn penalty file to use
  * An optional third argument is the shapefile to use to add shape points to the roadway network (to show road curvature, etc)
  * Optional shapefile outputs: -n to specify a node shapefile output, -l to specify a link shapefile output
 
 """

def addShifts(sanfranciscoCubeNet):
    """
    The San Francisco network has a few places where the roadway geometries need clarification via "shifts" --
    e.g. some local lanes need to be shifted to be outside the through lanes.
    """
    # geary local
    try:
        sanfranciscoCubeNet.getLinkForNodeIdPair(26594,26590).addShifts(3,3, addShapepoints=True)  # Steiner to Fillmore
        sanfranciscoCubeNet.getLinkForNodeIdPair(26590,26587).addShifts(3,3, addShapepoints=True)  # Fillmore to Webster
    except dta.DtaError as e:
        print e
    
    # geary - lyon 2 baker
    try:
        geary_lyon2baker = sanfranciscoCubeNet.getLinkForNodeIdPair(26835,26811)
        geary_lyon2baker.addShifts(0,1, addShapepoints=True) # shift access lane  
        geary_lyon2baker.findOutgoingMovement(26762)._outgoingLane = 1
    except dta.DtaError as e:
        print e

    try:
        sanfranciscoCubeNet.getLinkForNodeIdPair(26587,26590).addShifts(3,3, addShapepoints=True)  # Webster to Fillmore
        sanfranciscoCubeNet.getLinkForNodeIdPair(26590,26596).addShifts(3,3, addShapepoints=True)  # Fillmore to Avery
        sanfranciscoCubeNet.getLinkForNodeIdPair(26596,26594).addShifts(3,3, addShapepoints=True)  # Avery to Steiner
    except dta.DtaError as e:
        print e
        
    # broadway tunnel - access links
    try:
        sanfranciscoCubeNet.getLinkForNodeIdPair(25117,25111).addShifts(0,2, addShapepoints=True)  # Mason to Powell
    except dta.DtaError as e:
        print e
        
    # HWY 101 N On-Ramp at Marin / Bayshore
    try:
        sanfranciscoCubeNet.getLinkForNodeIdPair(33751,33083).addShifts(1,0, addShapepoints=True)
    except dta.DtaError as e:
        print e
        
    # Stockton SB to Post
    try:
        sanfranciscoCubeNet.getLinkForNodeIdPair(24907,24908).addShifts(0,1, addShapepoints=True)
    except dta.DtaError as e:
        print e
def addTurnPockets(sanfranciscoDynameqNet):
    """
    The San Francisco network has a few turn pockets -- add these.
    """
    # Post EB, Powell to Stockton has a block long turn pocket (right turn only)
    try:
        post_ebs = sanfranciscoDynameqNet.findLinksForRoadLabels(on_street_label="POST ST", on_direction=dta.RoadLink.DIR_EB,
                                                               from_street_label="POWELL ST", to_street_label="STOCKTON ST")
        for post_eb in post_ebs:
            post_eb.setNumLanes(3)
        
        # find the thru movement from post across stockton
        for mov in post_ebs[-1].iterOutgoingMovements():
            if mov.isThruTurn: mov.setNumLanes(2)
    except dta.DtaError as e:
        print e
    # Guerrero NB to Market has a right turn pocket

    try:
        guerrero_nbs = sanfranciscoDynameqNet.findLinksForRoadLabels(on_street_label="GUERRERO ST", on_direction=dta.RoadLink.DIR_NB,
                                                                    from_street_label="DUBOCE AVE", to_street_label="MARKET ST")
        guerrero_nbs[-1].setNumLanes(3)
    except dta.DtaError as e:
        print e    

def addCustomResFac(sanFranciscoCubeNet):
    """
    Adjusts response time factors for specific links
    """
    try:
        sanfranciscoCubeNet.getLinkForNodeIdPair(52158,52159).setResTimeFac(.8) #NB US-101 between hospital curve and Central Freeway split
    except dta.DtaError as e:
        print e


def addTollLink(sanFranciscoCubeNet):
    """
    Adjusts the tollLink field to match the Cube Network VALUETOLL_FLAG field (1 if the link is tolled, otherwise zero)
    """
    for link in sanfranciscoCubeNet.iterRoadLinks():
         VTF = int(sanfranciscoCubeNet.additionalLinkVariables[(link.getStartNode().getId(),link.getEndNode().getId())]['VALUETOLL_FLAG'])
         link.setTollLink(VTF)
        
def createTransitOnlyLanes(sanfranciscoCubeNet, allVCG, transitVCG):
    """
    Creates transit-only lanes based on the BUSLANE_PM field.
    """
    transit_lane_links = set()

    for link in sanfranciscoCubeNet.iterRoadLinks():
        ab_tuple = (link.getStartNode().getId(), link.getEndNode().getId())
        if ab_tuple not in sanfranciscoCubeNet.additionalLinkVariables: continue
        
        buslane_pm = int(sanfranciscoCubeNet.additionalLinkVariables[ab_tuple]["BUSLANE_PM"])
                
        # no transit lanes, don't worry about it
        if buslane_pm == 0: continue
        
        for lane_id in range(link.getNumLanes()):
            # around union square is special - right turn lanes exist to the right of buses
            if ab_tuple in [(24908,24906),  # Stockton SB, Post to Maiden Lane
                            (24906,24901),  # Stockton SB, Maiden Lane to Geary St
                            (24901,24903),  # Geary WB, Stockton to Powell
                            (24918,24908)]: # Post EB, Powell to Stockton
                if lane_id == 1 and (buslane_pm == 1 or buslane_pm == 2): 
                    link.addLanePermission(lane_id, transitVCG)
                    transit_lane_links.add(link.getId())
                else:
                    link.addLanePermission(lane_id, allVCG)
            # bush approaching market is special - left side
            elif ab_tuple in [(24679,24672)]: # Bush EB from Sansome to Battery
                if lane_id == link.getNumLanes()-1:
                    link.addLanePermission(lane_id, transitVCG)
                    transit_lane_links.add(link.getId())
                else:
                    link.addLanePermission(lane_id, allVCG)
            # diamond lane or side BRT lane1
            elif lane_id == 0 and (buslane_pm == 1 or buslane_pm == 2):
                link.addLanePermission(lane_id, transitVCG)
                transit_lane_links.add(link.getId())
            # center BRT lane
            elif lane_id == link.getNumLanes()-1 and buslane_pm == 3:
                link.addLanePermission(lane_id, transitVCG)
                transit_lane_links.add(link.getId())
            else:
                link.addLanePermission(lane_id, allVCG)
        
    dta.DtaLogger.info("Added transit lanes to %3d links" % len(transit_lane_links))
    logTransitOnlyLaneDistance(sanfranciscoCubeNet, transitVCG)

def encodeATintoFollowupTime(sanfranciscoCubeNet):
    """
    Hack: This is a hack way to pass Area Type to movements for later use. 
          This method sets Followup time to 90+AT value. 
    """
    for link in sanfranciscoCubeNet.iterRoadLinks():
        AT = int(sanfranciscoCubeNet.additionalLinkVariables[(link.getStartNode().getId(),link.getEndNode().getId())]['AT'])
        for mov in link.iterOutgoingMovements():
            mov.setFollowup(AT+90)
    
def logTransitOnlyLaneDistance(sanfranciscoCubeNet, transitVCG):
    """
    Tallies and logs how much transit-only lane we have (using link.getLength())
    """
    transit_lane_miles = 0.0
    for link in sanfranciscoCubeNet.iterRoadLinks():
        
        for lane_id in range(link.getNumLanes()):
            if link.getLanePermission(lane_id) == transitVCG:
                transit_lane_miles += link.getLength()
    dta.DtaLogger.info("The network has %.1f miles of transit lanes" % transit_lane_miles)

def allowTurnsFromTransitOnlyLanes(sanfranciscoCubeNet, allVCG, transitVCG, minLinkLength, splitForConnectors=False):
    """
    Looks at all the transit-only links and splits them to allow right or left turns for general traffic, if needed.
    
    Splits the link so that the transit section (which is at the start of the link) is *minLinkLength*.
    """
    right_splits = 0
    right_perms  = 0
    left_splits  = 0
    left_perms   = 0

    done         = False
    short_links_reverted = set() # link ids
    minLengthForSplit = 2.0*minLinkLength # would splitting it result in short links?
    
    # outter loop due to the fact we have to start searching for qualifying links again after we split since the iteration
    # will break once we update the roadlinks with a split
    while not done:
        
        did_split = False
        
        for link in sanfranciscoCubeNet.iterRoadLinks():
            
            # one lane - it doesn't matter
            if link.getNumLanes() == 1: continue
            
            ###################### check the right transit lane (lane 0) - are right turns allowed?
            lane_id = 0
            right_lane_perm = link.getLanePermission(lane_id)
            if right_lane_perm == transitVCG:
                
                right_turn_allowed = False
                
                for mov in link.iterOutgoingMovements():
                    # are right turns into general purpose lanes allowed?  (Not including into alleys)
                    if (mov.isRightTurn() and
                        mov.getVehicleClassGroup() == allVCG and
                        mov.getOutgoingLink().getFacilityType() != 10):
 
                        # if splitForConnectors is False and the right turn is a connector, it doesn't count
                        if not splitForConnectors and mov.getOutgoingLink().getFacilityType() == 99: continue
                        
                        right_turn_allowed = True
                
                if not right_turn_allowed: continue
                
                # is the link too short to split?  
                if link.getLength() < minLengthForSplit:
                    if link.getId() not in short_links_reverted:
                        short_links_reverted.add(link.getId())
                        dta.DtaLogger.debug("Transit link %d-%d too short to split or make transit only.  Reverting to general purpose lane." %
                                            (link.getStartNode().getId(), link.getEndNode().getId()))
                        link.addLanePermission(lane_id, allVCG)
                    continue
                
                # is the link already split?
                if link.getStartNode().getNumAdjacentNodes() == 2:
                    # dta.DtaLogger.debug("No need to split link %d for right turn from transit lane" % link.getId())
                    modlink = link
                else:
                    dta.DtaLogger.debug("Splitting link %d-%d for right turn from transit lane" %
                                        (link.getStartNode().getId(), link.getEndNode().getId()))
                    
                    # if the link is two way -- split in half.  otherwise, at minLinkLength
                    if sanfranciscoCubeNet.hasLinkForNodeIdPair(link.getEndNode().getId(), link.getStartNode().getId()):
                        fraction = 0.5
                    else:
                        fraction=minLinkLength/link.getLength()
                        
                    midnode = sanfranciscoCubeNet.splitLink(link, splitReverseLink=True, fraction=fraction)

                    newlink = sanfranciscoCubeNet.getLinkForNodeIdPair(link.getStartNode().getId(), midnode.getId())
                    modlink = sanfranciscoCubeNet.getLinkForNodeIdPair(midnode.getId(), link.getEndNode().getId())
                    
                    did_split = True
                    right_splits += 1
                
                modlink.addLanePermission(lane_id, allVCG)
                right_perms += 1
                
                # if the link was split then we have to start again, the iterRoadLinks() won't work anymore
                if did_split: break
            
            # This is repeated code because I didn't want to loop through right/left -- it would be less readable.
            
            ###################### check the left lane - are left turns allowed?
            lane_id = link.getNumLanes() - 1
            left_lane_perm = link.getLanePermission(lane_id)
            if left_lane_perm == transitVCG:
                
                left_turn_allowed = False
                
                for mov in link.iterOutgoingMovements():
                    # are left turns into general purpose lanes allowed?  (Not including into alleys)
                    if (mov.isLeftTurn() and
                        mov.getVehicleClassGroup() == allVCG and
                        mov.getOutgoingLink().getFacilityType() != 10):
 
                        # if splitForConnectors is False and the left turn is a connector, it doesn't count
                        if not splitForConnectors and mov.getOutgoingLink().getFacilityType() == 99: continue
                        
                        left_turn_allowed = True
                
                if not left_turn_allowed: continue

                # is the link too short to split?
                if link.getLength() < minLengthForSplit:
                    if link.getId() not in short_links_reverted:
                        short_links_reverted.add(link.getId())
                        dta.DtaLogger.debug("Transit link %d-%d too short to split or make transit only.  Reverting to general purpose lane." %
                                            (link.getStartNode().getId(), link.getEndNode().getId()))
                        link.addLanePermission(lane_id, allVCG)
                    continue
                                
                # is the link already split?
                if link.getStartNode().getNumAdjacentNodes() == 2:
                    # dta.DtaLogger.debug("No need to split link %d for left turn from transit lane" % link.getId())
                    modlink = link
                else:
                    dta.DtaLogger.debug("Splitting link %d-%d for left turn from transit lane" %
                                        (link.getStartNode().getId(), link.getEndNode().getId()))
                    midnode = sanfranciscoCubeNet.splitLink(link, splitReverseLink=True, fraction=0.5)

                    newlink = sanfranciscoCubeNet.getLinkForNodeIdPair(link.getStartNode().getId(), midnode.getId())
                    modlink = sanfranciscoCubeNet.getLinkForNodeIdPair(midnode.getId(), link.getEndNode().getId())
                    
                    did_split = True
                    left_splits += 1
                
                modlink.addLanePermission(lane_id, allVCG)
                left_perms += 1
                
                # if the link was split then we have to start again, the iterRoadLinks() won't work anymore
                if did_split: break
                
        
        # no splitting?? We're done!
        if not did_split: done = True
            
    dta.DtaLogger.info("Split %3d links for right turns from transit lanes, updated %3d permissions" % (right_splits, right_perms))
    dta.DtaLogger.info("Split %3d links for left  turns from transit lanes, updated %3d permissions" % (left_splits,  left_perms))
    dta.DtaLogger.info("Reverted %3d links to general purpose because splitting them would have resulted in short links" % len(short_links_reverted))
    logTransitOnlyLaneDistance(sanfranciscoCubeNet, transitVCG)
    
def removeHOVStubs(sanfranciscoDynameqNet):
    """
    The San Francisco network has a few "HOV stubs" -- links intended to facilitate future coding of HOV lanes
    Find these and remove them
    """    
    nodesToRemove = []
    for node in sanfranciscoDynameqNet.iterNodes():
        # one incomine link, one outgoing link
        if node.getNumIncomingLinks() != 1: continue
        if node.getNumOutgoingLinks() != 1: continue
        
        removalCandidate = True
        # the incoming/outgoing links must each be a road link of facility type 6
        for link in node.iterAdjacentLinks():
            if not link.isRoadLink(): 
                removalCandidate = False
                break
            if link.getFacilityType() != 9:
                removalCandidate = False
                break
        
        if removalCandidate:
            nodesToRemove.append(node)
    
    for node in nodesToRemove:
        dta.DtaLogger.info("Removing HOV Stub node %d" % node.getId())
        sanfranciscoDynameqNet.removeNode(node)

#: this_is_main
if __name__ == '__main__':
    
    optlist, args = getopt.getopt(sys.argv[1:], "n:l:")

    if len(args) <= 2:
        print USAGE
        sys.exit(2)
    
    SF_CUBE_NET_FILE            = args[0]
    SF_CUBE_TURN_PROHIBITIONS   = args[1]
    
    SF_CUBE_SHAPEFILE           = None
    if len(args) > 2:
        SF_CUBE_SHAPEFILE       = args[2]

    OUTPUT_NODE_SHAPEFILE       = None
    OUTPUT_LINK_SHAPEFILE       = None
    for (opt,arg) in optlist:
        if opt=="-n":
            OUTPUT_NODE_SHAPEFILE  = arg
        elif opt=="-l":
            OUTPUT_LINK_SHAPEFILE  = arg
            
    # The SanFrancisco network will use feet for vehicle lengths and coordinates, and miles for link lengths
    dta.VehicleType.LENGTH_UNITS= "feet"
    dta.Node.COORDINATE_UNITS   = "feet"
    dta.RoadLink.LENGTH_UNITS   = "miles"

    dta.setupLogging("createSFNetworkFromCubeNetwork.INFO.log", "createSFNetworkFromCubeNetwork.DEBUG.log", logToConsole=True)
        
    # The rest of San Francisco currently exists as a Cube network.  Initialize it from
    # the Cube network files (which have been exported to dbfs.)
    # This is where we define the :py:class:`dta.Scenario`
    sanfranciscoScenario = dta.DynameqScenario(dta.Time(14,30), dta.Time(21,30))

    # We will have 4 vehicle classes: Car_NoToll, Car_Toll, Truck_NoToll, Truck_Toll 
    # We will provide demand matrices for each of these classes
    sanfranciscoScenario.addVehicleClass("Car_NoToll")
    sanfranciscoScenario.addVehicleClass("Car_Toll")
    sanfranciscoScenario.addVehicleClass("Truck_NoToll")
    sanfranciscoScenario.addVehicleClass("Truck_Toll")
    # Transit is an implicit type
    
    # length is in feet (from above), response time is in seconds, maxSpeed is in mi/hour
    # We have only 2 vehicle types                      Type        VehicleClass    Length  RespTime    MaxSpeed    SpeedRatio
    sanfranciscoScenario.addVehicleType(dta.VehicleType("Car",      "Car_NoToll",   21,       1,       100.0,      100.0))
    sanfranciscoScenario.addVehicleType(dta.VehicleType("Car",      "Car_Toll",     21,       1,       100.0,      100.0))
    sanfranciscoScenario.addVehicleType(dta.VehicleType("Truck",    "Truck_NoToll", 31.5,  1.25,        70.0,       90.0))
    sanfranciscoScenario.addVehicleType(dta.VehicleType("Truck",    "Truck_Toll",   31.5,  1.25,        70.0,       90.0))
    sanfranciscoScenario.addVehicleType(dta.VehicleType("LRT1",     "Transit",      75,     1.6,        35.0,       90.0))
    sanfranciscoScenario.addVehicleType(dta.VehicleType("LRT2",     "Transit",     150,     1.6,        35.0,       90.0))
    sanfranciscoScenario.addVehicleType(dta.VehicleType("Trolley_Std",  "Transit",  40,     1.6,        70.0,       90.0))
    sanfranciscoScenario.addVehicleType(dta.VehicleType("Trolley_Artic","Transit",  60,     1.6,        70.0,       90.0))
    sanfranciscoScenario.addVehicleType(dta.VehicleType("Motor_Std",    "Transit",  40,     1.6,        70.0,       90.0))
    sanfranciscoScenario.addVehicleType(dta.VehicleType("Motor_Artic",  "Transit",  60,     1.6,        70.0,       90.0))
    sanfranciscoScenario.addVehicleType(dta.VehicleType("CableCar",     "Transit",  27.5,   1.6,         9.5,       90.0))    
    dta.DtaLogger.info("Maximum vehicle length = %f" % sanfranciscoScenario.maxVehicleLength())
    # Generic is an implicit type

    # VehicleClassGroups
    allVCG     = dta.VehicleClassGroup(dta.VehicleClassGroup.CLASSDEFINITION_ALL,        dta.VehicleClassGroup.CLASSDEFINITION_ALL,          "#bebebe")
    transitVCG = dta.VehicleClassGroup(dta.VehicleClassGroup.CLASSDEFINITION_TRANSIT,    dta.VehicleClassGroup.CLASSDEFINITION_TRANSIT,      "#55ff00")
    sanfranciscoScenario.addVehicleClassGroup(allVCG)
    sanfranciscoScenario.addVehicleClassGroup(transitVCG)
    sanfranciscoScenario.addVehicleClassGroup(dta.VehicleClassGroup(dta.VehicleClassGroup.CLASSDEFINITION_PROHIBITED, dta.VehicleClassGroup.CLASSDEFINITION_PROHIBITED,   "#ffff00"))
    sanfranciscoScenario.addVehicleClassGroup(dta.VehicleClassGroup("Toll",                           "Car_Toll|Truck_Toll",                              "#0055ff"))
        
    # Generalized cost
    # TODO: Make this better!?!
    sanfranciscoScenario.addGeneralizedCost("Expression_0", # name
                                            "Seconds",      # units
                                            "ptime+(left_turn_pc*left_turn)+(right_turn_pc*right_turn)", # turn_expr
                                            "0",            # link_expr
                                            ""              # descr
                                            )

    sanfranciscoScenario.addGeneralizedCost("Expression_1", # name
                                            "Seconds",      # units
                                            "ptime+(left_turn_pc*left_turn)+(right_turn_pc*right_turn)", # turn_expr
                                            "fac_type_pen*(3600*length/fspeed)",            # link_expr
                                            ""              # descr
                                            )
    sanfranciscoScenario.addGeneralizedCost("Expression_2", # name
                                            "Seconds",      # units
                                            "ptime+(left_turn_pc*left_turn)+(right_turn_pc*right_turn)", # turn_expr
                                            "14.4*length",            # link_expr
                                            ""              # descr
                                            )
    sanfranciscoScenario.addGeneralizedCost("Expression_3", # name
                                            "Seconds",      # units
                                            "ptime+(left_turn_pc*left_turn)+(right_turn_pc*right_turn)", # turn_expr
                                            "14.4*length+fac_type_pen*(1800*length/fspeed)",            # link_expr
                                            ""              # descr
                                            )
    sanfranciscoScenario.addGeneralizedCost("Expression_4", # name
                                            "Seconds",      # units
                                            "ptime+(left_turn_pc*left_turn)+(right_turn_pc*right_turn)", # turn_expr
                                            "fac_type_pen*(1800*length/fspeed)",            # link_expr
                                            ""              # descr
                                            )    
    sanfranciscoScenario.addGeneralizedCost("Expression_5", # name
                                            "Seconds",      # units
                                            "ptime+(left_turn_pc*left_turn)+(right_turn_pc*right_turn)", # turn_expr
                                            "fac_type_pen*(1800*length/fspeed)+(value_toll*379)",            # link_expr
                                            "For Car_Toll - Local and collector penalties and $3 (2012$) toll for tolled links"              # descr
                                            )    
    sanfranciscoScenario.addGeneralizedCost("Expression_6", # name
                                            "Seconds",      # units
                                            "ptime+(left_turn_pc*left_turn)+(right_turn_pc*right_turn)", # turn_expr
                                            "fac_type_pen*(1800*length/fspeed)+(value_toll*10000)",            # link_expr
                                            "For Car_Notoll - Local and collector penalties and prohibitive toll for tolled links"              # descr
                                            )  
    # Read the Cube network
    sanfranciscoCubeNet = dta.CubeNetwork(sanfranciscoScenario)
    centroidIds         = range(1,982)  # centroids 1-981 are internal to SF
    boundaryIds         = [1204,1205,1207,1191,1192,1206,6987,6994,7144,7177,
                           7654,7677,7678,7705,7706,7709,7721,7972,7973,8338,
                           8339,8832]     # externals
    centroidIds.extend(boundaryIds)
   
    # Calculated for freeways and expressways based on Caltrans sensors for freeways in SF
    # Updated for locals/collectors and arterials based on second round MTA speed data
    # Decreased locals/collectors' FFS (especially in residential areas)to account for FF Sapce-Mean-Speed along acc/dec segments before and after stop signs
    # Not to be used with generelized cost function : Expression_1
    speedLookup = { \
        'FT1 AT0':35, 'FT1 AT1':40, 'FT1 AT2':45, 'FT1 AT3':45, 'FT1 AT4':55, 'FT1 AT5':55, 
        'FT2 AT0':60, 'FT2 AT1':65, 'FT2 AT2':65, 'FT2 AT3':65, 'FT2 AT4':70, 'FT2 AT5':70, 
        'FT3 AT0':60, 'FT3 AT1':65, 'FT3 AT2':65, 'FT3 AT3':65, 'FT3 AT4':65, 'FT3 AT5':65, 
        'FT4 AT0':23, 'FT4 AT1':23, 'FT4 AT2':20, 'FT4 AT3':20, 'FT4 AT4':35, 'FT4 AT5':35, 
        'FT5 AT0':30, 'FT5 AT1':30, 'FT5 AT2':35, 'FT5 AT3':35, 'FT5 AT4':40, 'FT5 AT5':40, 
        'FT7 AT0':28, 'FT7 AT1':28, 'FT7 AT2':30, 'FT7 AT3':32, 'FT7 AT4':40, 'FT7 AT5':40, 
        'FT9 AT0':10, 'FT9 AT1':10, 'FT9 AT2':10, 'FT9 AT3':10, 'FT9 AT4':10, 'FT9 AT5':10,         
        'FT11 AT0':18, 'FT11 AT1':18, 'FT11 AT2':18, 'FT11 AT3':15, 'FT11 AT4':35, 'FT11 AT5':35, 
        'FT12 AT0':26, 'FT12 AT1':26, 'FT12 AT2':28, 'FT12 AT3':30, 'FT12 AT4':40, 'FT12 AT5':40, 
        'FT15 AT0':30, 'FT15 AT1':30, 'FT15 AT2':33, 'FT15 AT3':36, 'FT15 AT4':50, 'FT15 AT5':50, 
    }
    # Rise dependent response times from traffic flow study
    responseTimeLookup = { \
    	'FLAT' : 1.0,	'UP' : 1.1,	'DOWN' : 0.9,
    }      
    # see http://code.google.com/p/dta/wiki/NetworkDescriptionForSF
    ftToDTALookup = {"2":1,
                     "3":2,
                     "1":3,
                     "7":4,
                     "15":4,
                     "12":5,
                     "4":6,
                     "11":7,
                     "5":8,
                     # centroid connectors should be what?
                     "6":9,
                     "9":10,
                     }
    
    # Lookup effective length factor (currently set to be 0.95 downtown - AT0&AT1 - and 1.00 elsewhere)
    linkEffectiveLengthFactorLookup = {"AT0":0.95, "AT1":0.95, "AT2":1.0, "AT3":1.0, "AT4":1.0, "AT5":1.0,}
    
    # What is the largest link effective length factor?
    maxLinkEffectiveLengthFactor=max(linkEffectiveLengthFactorLookup.values())

    # We can now calculate minimum link length
    SF_MIN_LINK_LENGTH = round(maxLinkEffectiveLengthFactor*sanfranciscoScenario.maxVehicleLength()/5280.0 + 0.0005,3)
    
    sanfranciscoCubeNet.readNetfile \
      (netFile=SF_CUBE_NET_FILE,
       nodeVariableNames=["N","X","Y","OLD_NODE"],
       linkVariableNames=["A","B","TOLL","USE",
                          "CAP","AT","FT","STREETNAME","TYPE",
                          "MTYPE","SPEED","DISTANCE","TIME",
                          "LANE_AM","LANE_OP","LANE_PM",
                          "BUSLANE_AM","BUSLANE_OP","BUSLANE_PM",
                          "TOLLAM_DA","TOLLAM_SR2","TOLLAM_SR3",
                          "TOLLPM_DA","TOLLPM_SR2","TOLLPM_SR3",
                          "TOLLEA_DA","TOLLEA_SR2","TOLLEA_SR3",
                          "TOLLMD_DA","TOLLMD_SR2","TOLLMD_SR3",
                          "TOLLEV_DA","TOLLEV_SR2","TOLLEV_SR3 ",
                          "VALUETOLL_FLAG","PASSTHRU",
                          "BUSTPS_AM","BUSTPS_OP","BUSTPS_PM",
                          "TSVA","TSIN","BIKE_CLASS","PER_RISE",
     #                    "ONEWAY","PROJ","DTA_EDIT_FL","TOLLTIME",
                          ],
       centroidIds                      = centroidIds,
       useOldNodeForId                  = True,
       nodeGeometryTypeEvalStr          = "Node.GEOMETRY_TYPE_INTERSECTION",
       nodeControlEvalStr               = "RoadNode.CONTROL_TYPE_UNSIGNALIZED",
       nodePriorityEvalStr              = "RoadNode.PRIORITY_TEMPLATE_NONE",
       nodeLabelEvalStr                 = "'boundary' if int(OLD_NODE) in boundaryIds else None",
       nodeLevelEvalStr                 = "None",
       linkReverseAttachedIdEvalStr     = "None", #TODO: fix?
       linkFacilityTypeEvalStr          = "ftToDTALookup[FT]",
       linkLengthEvalStr                = "float(DISTANCE)",
       linkFreeflowSpeedEvalStr         = "45.0 if FT=='6' else float(speedLookup['FT'+FT+' AT'+AT])",
       linkEffectiveLengthFactorEvalStr = "float(linkEffectiveLengthFactorLookup['AT'+AT])",
       linkResponseTimeFactorEvalStr    = "1 if FT=='6' else 1 if FT=='1' else 1 if FT=='2' else 1 if FT=='3' else float(responseTimeLookup['UP' if (float(PER_RISE) > 0.05) else ('FLAT' if (float(PER_RISE) > -0.05) else 'DOWN')])",
       linkNumLanesEvalStr              = "2 if isConnector else (int(LANE_PM) + (1 if int(BUSLANE_PM)>0 else 0))",
       linkRoundAboutEvalStr            = "False",
       linkLevelEvalStr                 = "None",
       linkLabelEvalStr                 = '(STREETNAME if STREETNAME else "") + (" " if TYPE and STREETNAME else "") + (TYPE if TYPE else "")',
       linkGroupEvalStr                 = "-1",
       linkSkipEvalStr                  = "FT=='13'", # skip bike-only
       additionalLocals                 = {'ftToDTALookup':ftToDTALookup,
                                           'speedLookup':speedLookup,
                                           'responseTimeLookup':responseTimeLookup,
                                           'boundaryIds':boundaryIds,
                                           'linkEffectiveLengthFactorLookup':linkEffectiveLengthFactorLookup,
                                           })
    # Apply the transit lanes
    createTransitOnlyLanes(sanfranciscoCubeNet, allVCG, transitVCG)
        
    # create the movements for the network for all vehicles
    sanfranciscoCubeNet.addAllMovements(allVCG, includeUTurns=False)

    # HACK: make movement followup times code for AT of the incoming links
    encodeATintoFollowupTime(sanfranciscoCubeNet)

    # Apply the turn prohibitions
    sanfranciscoCubeNet.applyTurnProhibitions(SF_CUBE_TURN_PROHIBITIONS)
    
    # Read the shape points so curvy streets look curvy
    # 3, 4 are the Broadway Tunnel, being routed too far south in GIS file
    # 5234 # Skip this one link at Woodside/Portola because it overlaps
    # 2798, # Skip this Central Freeway link because Dynameq hates it but I DON'T KNOW WHY
    if SF_CUBE_SHAPEFILE:
        sanfranciscoCubeNet.readLinkShape(SF_CUBE_SHAPEFILE, "A", "B",
                                          skipEvalStr="(OBJECTID in [3,4,5234,2798]) or (MEDIANDIV==1)")
     
    # Some special links needing shifts
    addShifts(sanfranciscoCubeNet)
    
    #Some special links need special response times (in one case to mitigate over-penalizing capacity due to high percent of lane changes)
    addCustomResFac(sanfranciscoCubeNet)

    #Some links may have a toll. Change tollLink field from 0 to 1 if link is tolled
    addTollLink(sanfranciscoCubeNet)
    
    # Convert the network to a Dynameq DTA network
    sanfranciscoDynameqNet = dta.DynameqNetwork(scenario=sanfranciscoScenario)
    sanfranciscoDynameqNet.deepcopy(sanfranciscoCubeNet)
    
    # the San Francisco network has a few "HOV stubs" -- links intended to facilitate future coding of HOV lanes
    removeHOVStubs(sanfranciscoDynameqNet)
    
    # Battery between Bush and Market is a parking garage - forcibly split it
    try:
        battery_sbs = sanfranciscoDynameqNet.findLinksForRoadLabels(on_street_label="BATTERY ST", on_direction=dta.RoadLink.DIR_SB,
                                                                   from_street_label="BUSH ST", to_street_label="MARKET ST")
        if len(battery_sbs) == 1: sanfranciscoDynameqNet.splitLink(battery_sbs[0])
    except dta.DtaError as e:
        print e

    # Add virtual nodes and links between Centroids and RoadNodes; required by Dynameq        
    sanfranciscoDynameqNet.insertVirtualNodeBetweenCentroidsAndRoadNodes(startVirtualNodeId=9000000, startVirtualLinkId=9000000,
                                                                         distanceFromCentroid=50)
    
    # Move the centroid connectors from intersection nodes to midblock locations
    # TODO: for dead-end streets, is this necessary?  Or are the midblocks ok?        
    sanfranciscoDynameqNet.moveCentroidConnectorsFromIntersectionsToMidblocks(splitReverseLinks=True, moveVirtualNodeDist=50, externalNodeIds=boundaryIds, 
                                                                              disallowConnectorEvalStr="True if self.getFacilityType() in [1,8] else False")

    # Allow turns from transit lanes -- this needs to be done after the centroid connectors are moved or they interfere connecting
    # to intersections
    allowTurnsFromTransitOnlyLanes(sanfranciscoDynameqNet, allVCG, transitVCG, minLinkLength=SF_MIN_LINK_LENGTH, splitForConnectors=False)

    # Some special links needing turn pockets
    addTurnPockets(sanfranciscoDynameqNet)
    
    # Add Two-Way stop control to connectors, so vehicles coming out of connectors yield to the vehicles already on the street
    sanfranciscoDynameqNet.addTwoWayStopControlToConnectorsAtRoadlinks()

    # Warn on overlapping links, and move virtual nodes up to 100 feet if that helps
    sanfranciscoDynameqNet.handleOverlappingLinks(warn=True, moveVirtualNodeDist=100)
    
    # finally -- Dynameq requires links to be longer than the longest vehicle x the linkEffectiveLengthFactor
    # rounding up because the lengths are specified with 3 decimals in the file, so if they happen to round down they're too short
    sanfranciscoDynameqNet.handleShortLinks(SF_MIN_LINK_LENGTH,
                                            warn=True,
                                            setLength=True)

    # if we have too many nodes for the license 10
    if sanfranciscoDynameqNet.getNumRoadNodes() > 12500:
        sanfranciscoDynameqNet.removeUnconnectedNodes()
    sanfranciscoDynameqNet.write(dir=r".", file_prefix="sf")
 
    # export the network as shapefiles if requested 
    if OUTPUT_NODE_SHAPEFILE: sanfranciscoDynameqNet.writeNodesToShp(OUTPUT_NODE_SHAPEFILE)
    if OUTPUT_LINK_SHAPEFILE: sanfranciscoDynameqNet.writeLinksToShp(OUTPUT_LINK_SHAPEFILE) 
 
    
    
