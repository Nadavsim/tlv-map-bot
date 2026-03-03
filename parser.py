import xml.etree.ElementTree as ET
import pandas as pd

def parse_kml_to_csv(kml_file_path: str, output_csv_path: str) -> None:
    # KML files use an XML namespace, we have to define it to search the tree
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    
    # Load the XML tree
    tree = ET.parse(kml_file_path)
    root = tree.getroot()
    
    places_data = []

    # Iterate through every 'Folder' (which represents your My Maps layers)
    for folder in root.findall('.//kml:Folder', ns):
        
        # 1. Safely extract the Category Name
        folder_name_node = folder.find('kml:name', ns)
        category_name = folder_name_node.text if folder_name_node is not None and folder_name_node.text else 'Uncategorized'
        
        # Iterate through every 'Placemark' inside this folder
        for placemark in folder.findall('.//kml:Placemark', ns):
            
            # 2. Safely extract the Place Name
            place_name_node = placemark.find('kml:name', ns)
            place_name = place_name_node.text if place_name_node is not None and place_name_node.text else 'Unknown'
            
            # 3. Safely extract and parse the Coordinates
            coords_node = placemark.find('.//kml:coordinates', ns)
            
            # We strictly check that the node exists AND that it contains text
            if coords_node is not None and coords_node.text is not None:
                coords = coords_node.text.strip().split(',')
                
                # Ensure we actually got both longitude and latitude back
                if len(coords) >= 2:
                    longitude = float(coords[0])
                    latitude = float(coords[1])
                    
                    places_data.append({
                        'Name': place_name,
                        'Category': category_name,
                        'Latitude': latitude,
                        'Longitude': longitude
                    })

    # Convert to a DataFrame and export to CSV
    df = pd.DataFrame(places_data)
    df.to_csv(output_csv_path, index=False)
    print(f"Success! Extracted {len(df)} places into {output_csv_path}")
    print(df.head())

if __name__ == "__main__":
    # Make sure your exported map file is named 'map.kml' and is in the same folder
    parse_kml_to_csv('map.kml', 'cleaned_places.csv')