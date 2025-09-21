"""
MarineTraffic Link Builder v1.0
Generates deep-links to MarineTraffic for vessel and port visualization
Following vendor-agnostic specification for URL patterns
"""

from typing import Dict, Optional, Any
import re
from dataclasses import dataclass


@dataclass
class MarineTrafficLinks:
    """Container for generated MarineTraffic URLs"""
    url_details: Optional[str] = None        # Vessel detail page
    url_map_vessel: Optional[str] = None     # Map centered on vessel
    url_map_coords: Optional[str] = None     # Map centered on coordinates
    url_embed: Optional[str] = None          # Embeddable iframe
    url_port: Optional[str] = None           # Port detail page


class MarineTrafficLinkBuilder:
    """
    Builds MarineTraffic deep-links based on vessel and location data
    Supports IMO, MMSI, ShipID, coordinates, and port information
    """
    
    BASE_URL = "https://www.marinetraffic.com"
    DEFAULT_ZOOM = 9
    DEFAULT_EMBED_ZOOM = 10
    
    # Known port IDs for common Brazilian ports
    PORT_IDS = {
        "BRSSZ": 189,  # Santos
        "BRRIO": 188,  # Rio de Janeiro  
        "BRPNG": 185,  # Paranaguá
        "BRSPB": 190,  # São Sebastião
        "BRSJZ": 191,  # São Francisco do Sul
    }

    @classmethod
    def build_links(
        cls,
        imo: Optional[str] = None,
        mmsi: Optional[str] = None,
        shipid: Optional[str] = None,
        vessel_name: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        zoom: Optional[int] = None,
        port_code: Optional[str] = None,
        port_id: Optional[int] = None,
        language: str = "en"
    ) -> MarineTrafficLinks:
        """
        Build all relevant MarineTraffic links based on available data
        
        Args:
            imo: 7-digit IMO number (preferred identifier)
            mmsi: 9-digit MMSI number 
            shipid: MarineTraffic internal ship ID
            vessel_name: Vessel name (cosmetic only, not used in URLs)
            lat: Latitude for coordinate-based links
            lon: Longitude for coordinate-based links  
            zoom: Map zoom level (3-18, default 9)
            port_code: Port code (e.g., "BRSSZ" for Santos)
            port_id: MarineTraffic port ID (e.g., 189 for Santos)
            language: Language code ("en" or "pt")
            
        Returns:
            MarineTrafficLinks object with generated URLs
        """
        
        links = MarineTrafficLinks()
        zoom = zoom or cls.DEFAULT_ZOOM
        
        # Sanitize inputs
        imo = cls._sanitize_imo(imo)
        mmsi = cls._sanitize_mmsi(mmsi)
        shipid = cls._sanitize_shipid(shipid)
        
        # 1. Vessel details URL (prefer IMO > MMSI > ShipID)
        links.url_details = cls._build_details_url(imo, mmsi, shipid, language)
        
        # 2. Map focused on vessel
        links.url_map_vessel = cls._build_map_vessel_url(shipid, language)
        
        # 3. Map centered on coordinates
        if lat is not None and lon is not None:
            links.url_map_coords = cls._build_map_coords_url(lat, lon, zoom, language)
        
        # 4. Embeddable iframe
        if mmsi:
            links.url_embed = cls._build_embed_url(mmsi, zoom, language)
        
        # 5. Port details
        if port_id:
            links.url_port = cls._build_port_url(port_id, language)
        elif port_code and port_code in cls.PORT_IDS:
            links.url_port = cls._build_port_url(cls.PORT_IDS[port_code], language)
        
        return links

    @classmethod
    def _build_details_url(
        cls, 
        imo: Optional[str], 
        mmsi: Optional[str], 
        shipid: Optional[str], 
        language: str
    ) -> Optional[str]:
        """Build vessel details URL with identifier preference: IMO > MMSI > ShipID"""
        
        if imo:
            return f"{cls.BASE_URL}/{language}/ais/details/ships/imo:{imo}"
        elif mmsi:
            return f"{cls.BASE_URL}/{language}/ais/details/ships/mmsi:{mmsi}"
        elif shipid:
            return f"{cls.BASE_URL}/{language}/ais/details/ships/shipid:{shipid}"
        
        return None

    @classmethod
    def _build_map_vessel_url(cls, shipid: Optional[str], language: str) -> Optional[str]:
        """Build map URL focused on specific vessel"""
        
        if shipid:
            return f"{cls.BASE_URL}/{language}/ais/home/shipid:{shipid}"
        
        return None

    @classmethod
    def _build_map_coords_url(
        cls, 
        lat: float, 
        lon: float, 
        zoom: int, 
        language: str
    ) -> str:
        """Build map URL centered on coordinates"""
        
        return f"{cls.BASE_URL}/{language}/ais/home/centerx:{lon}/centery:{lat}/zoom:{zoom}"

    @classmethod
    def _build_embed_url(cls, mmsi: str, zoom: int, language: str) -> str:
        """Build embeddable iframe URL"""
        
        embed_zoom = zoom or cls.DEFAULT_EMBED_ZOOM
        return f"{cls.BASE_URL}/{language}/ais/embed/showmenu:false/shownames:false/mmsi:{mmsi}/zoom:{embed_zoom}"

    @classmethod
    def _build_port_url(cls, port_id: int, language: str) -> str:
        """Build port details URL"""
        
        # Special handling for Santos port
        if port_id == 189:
            return f"{cls.BASE_URL}/{language}/ais/details/ports/{port_id}?country=Brazil&name=SANTOS"
        else:
            return f"{cls.BASE_URL}/{language}/ais/details/ports/{port_id}"

    @classmethod
    def _sanitize_imo(cls, imo: Optional[str]) -> Optional[str]:
        """Sanitize and validate IMO number"""
        if not imo:
            return None
            
        # Remove any non-digits and ensure 7 digits
        imo_clean = re.sub(r'\D', '', str(imo))
        if len(imo_clean) == 7:
            return imo_clean
            
        return None

    @classmethod
    def _sanitize_mmsi(cls, mmsi: Optional[str]) -> Optional[str]:
        """Sanitize and validate MMSI number"""
        if not mmsi:
            return None
            
        # Remove any non-digits and ensure 9 digits
        mmsi_clean = re.sub(r'\D', '', str(mmsi))
        if len(mmsi_clean) == 9:
            return mmsi_clean
            
        return None

    @classmethod
    def _sanitize_shipid(cls, shipid: Optional[str]) -> Optional[str]:
        """Sanitize ShipID"""
        if not shipid:
            return None
            
        # Convert to string and remove any non-alphanumeric characters
        return re.sub(r'[^a-zA-Z0-9]', '', str(shipid))

    @classmethod
    def get_santos_port_links(cls, language: str = "en") -> MarineTrafficLinks:
        """Get MarineTraffic links for Santos Port"""
        
        # Santos port coordinates
        santos_lat = -23.9534
        santos_lon = -46.3334
        
        return cls.build_links(
            lat=santos_lat,
            lon=santos_lon,
            port_code="BRSSZ",
            zoom=12,
            language=language
        )


# Utility functions for easy integration
def create_vessel_links(vessel_data: Dict[str, Any]) -> MarineTrafficLinks:
    """
    Create MarineTraffic links from vessel data dictionary
    Extracts relevant fields and builds links
    """
    
    return MarineTrafficLinkBuilder.build_links(
        imo=vessel_data.get("imo"),
        mmsi=vessel_data.get("mmsi"),
        shipid=vessel_data.get("shipid"),
        vessel_name=vessel_data.get("vessel_name"),
        lat=vessel_data.get("latitude"),
        lon=vessel_data.get("longitude")
    )


def create_port_links(coordinates: tuple = (-23.9534, -46.3334)) -> MarineTrafficLinks:
    """Create MarineTraffic links for port view (default: Santos)"""
    
    lat, lon = coordinates
    return MarineTrafficLinkBuilder.build_links(
        lat=lat,
        lon=lon,
        port_code="BRSSZ",
        zoom=11
    )


# Example usage and testing
if __name__ == "__main__":
    # Test with the LOG IN DISCOVERY vessel mentioned in the spec
    test_vessel = {
        "imo": "9506394",
        "mmsi": "710006293", 
        "shipid": "714410",
        "vessel_name": "LOG IN DISCOVERY"
    }
    
    links = create_vessel_links(test_vessel)
    
    print("MarineTraffic Links for LOG IN DISCOVERY:")
    print(f"Details: {links.url_details}")
    print(f"Map Vessel: {links.url_map_vessel}")
    print(f"Embed: {links.url_embed}")
    
    # Test Santos port links
    port_links = create_port_links()
    print(f"\nSantos Port: {port_links.url_port}")
    print(f"Santos Map: {port_links.url_map_coords}")