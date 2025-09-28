#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'analyse forensique de données de géolocalisation
Analyse les fichiers .dat de dashcam et génère une visualisation interactive
"""

import pandas as pd
import folium
import tkinter as tk
from tkinter import filedialog, messagebox
import webbrowser
import os
from datetime import datetime
import re
import json
from datetime import timedelta


class DashcamAnalyzer:
    def __init__(self):
        self.df = None
        self.map = None
        
    def select_file(self):
        """Interface graphique pour sélectionner plusieurs fichiers .dat"""
        root = tk.Tk()
        root.withdraw()  # Masquer la fenêtre principale
        
        file_paths = filedialog.askopenfilenames(
            title="Sélectionner un ou plusieurs fichiers de données .dat",
            filetypes=[("Fichiers DAT", "*.dat"), ("Tous les fichiers", "*.*")]
        )
        
        root.destroy()
        return file_paths
    
    def read_and_parse_data(self, file_path):
        """Lire et parser les données du fichier .dat"""
        print(f"Lecture du fichier : {file_path}")
        
        data_lines = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line_num, line in enumerate(file, 1):
                    line = line.strip()
                    
                    # Ignorer les lignes vides et les commentaires
                    if not line or line.startswith('#'):
                        continue
                    
                    # Vérifier si la ligne commence par un horodatage valide (14 chiffres)
                    if re.match(r'^\d{14},', line):
                        parts = line.split(',')
                        if len(parts) >= 7:
                            data_lines.append(parts)
                        else:
                            print(f"Ligne {line_num} ignorée - format invalide : {line}")
                    else:
                        print(f"Ligne {line_num} ignorée - ne commence pas par un horodatage : {line}")
        
        except Exception as e:
            raise Exception(f"Erreur lors de la lecture du fichier : {e}")
        
        if not data_lines:
            raise Exception("Aucune donnée valide trouvée dans le fichier")
        
        # Créer le DataFrame
        self.df = pd.DataFrame(data_lines, columns=[
            'timestamp_str', 'lat', 'lat_indicator', 'lon', 'lon_indicator', 'data_1', 'data_2'
        ])
        
        print(f"Données chargées : {len(self.df)} points de géolocalisation")
        return self.df
    
    def clean_and_transform_data(self):
        """Nettoyer et transformer les données"""
        print("Nettoyage et transformation des données...")
        
        # Convertir l'horodatage
        self.df['datetime'] = pd.to_datetime(self.df['timestamp_str'], format='%Y%m%d%H%M%S')
        
        # Convertir les coordonnées GPS
        # Latitude
        self.df['latitude'] = pd.to_numeric(self.df['lat'])
        self.df.loc[self.df['lat_indicator'] == 'S', 'latitude'] *= -1
        
        # Longitude
        self.df['longitude'] = pd.to_numeric(self.df['lon'])
        self.df.loc[self.df['lon_indicator'] == 'W', 'longitude'] *= -1
        
        # Convertir les données supplémentaires
        self.df['data_1'] = pd.to_numeric(self.df['data_1'])
        self.df['data_2'] = pd.to_numeric(self.df['data_2'])
        
        # Créer les informations pour le popup
        self.df['popup_info'] = (
            "<b>Horodatage:</b> " + self.df['datetime'].dt.strftime('%d/%m/%Y %H:%M:%S') + "<br>" +
            "<b>Latitude:</b> " + self.df['latitude'].round(6).astype(str) + "°<br>" +
            "<b>Longitude:</b> " + self.df['longitude'].round(6).astype(str) + "°<br>" +
            "<b>Donnée 1:</b> " + self.df['data_1'].round(3).astype(str) + "<br>" +
            "<b>Donnée 2:</b> " + self.df['data_2'].round(3).astype(str)
        )
        
        # Trier par horodatage
        self.df = self.df.sort_values('datetime').reset_index(drop=True)
        
        # Détection des trajets basée sur les interruptions temporelles
        self.df['time_diff'] = self.df['datetime'].diff().dt.total_seconds().fillna(0)
        trip_threshold = 30 * 60  # 30 minutes en secondes
        
        # Appliquer la détection par jour si la colonne day_id existe
        if 'day_id' in self.df.columns:
            self.df['trip_id'] = self.df.groupby('day_id')['time_diff'].transform(lambda x: (x > trip_threshold).cumsum())
        else:
            self.df['trip_id'] = (self.df['time_diff'] > trip_threshold).cumsum()

        num_trips = len(self.df.groupby(['day_id', 'trip_id'])) if 'day_id' in self.df.columns else self.df['trip_id'].nunique()
        print(f"Détection de {num_trips} trajets distincts au total.")
        
        print(f"Données transformées : {len(self.df)} points triés chronologiquement")
        print(f"Période : {self.df['datetime'].min()} à {self.df['datetime'].max()}")
        
        return self.df
    
    def create_interactive_map(self):
        """Créer la carte interactive avec folium"""
        print("Création de la carte interactive...")
        
        # Créer la carte en full screen
        self.map = folium.Map(
            location=[self.df['latitude'].mean(), self.df['longitude'].mean()],
            zoom_start=15
        )
        
        # Ajouter une ligne de trajet grisée (tous les points)
        if len(self.df) > 1:
            coordinates = [[row['latitude'], row['longitude']] for _, row in self.df.iterrows()]
            folium.PolyLine(
                locations=coordinates,
                color='gray',
                weight=3,
                opacity=0.5,
                dash_array='5, 5'
            ).add_to(self.map)
        
        print("Carte interactive créée avec succès")
        return self.map
    
    def add_timeslider(self):
        """Ajouter un slider temporel interactif"""
        print("Ajout du slider temporel...")
        
        # Préparer les données pour le slider
        start_time = self.df['datetime'].min()
        end_time = self.df['datetime'].max()
        total_seconds = int((end_time - start_time).total_seconds())
        
        # Créer des groupes temporels (toutes les 30 secondes)
        time_groups = []
        current_time = start_time
        group_index = 0
        
        while current_time <= end_time:
            next_time = current_time + pd.Timedelta(seconds=30)
            group_data = self.df[
                (self.df['datetime'] >= current_time) & 
                (self.df['datetime'] < next_time)
            ]
            
            if not group_data.empty:
                time_groups.append({
                    'index': group_index,
                    'time': current_time,
                    'time_str': current_time.strftime('%H:%M:%S'),
                    'data': group_data
                })
                group_index += 1
            
            current_time = next_time
        
        # Ajouter des marqueurs de début et fin
        start_row = self.df.iloc[0]
        folium.Marker(
            location=[start_row['latitude'], start_row['longitude']],
            popup=folium.Popup(f"<b>DÉBUT DU TRAJET</b><br>{start_row['popup_info']}", max_width=300),
            icon=folium.Icon(color='green', icon='play', prefix='fa')
        ).add_to(self.map)
        
        end_row = self.df.iloc[-1]
        folium.Marker(
            location=[end_row['latitude'], end_row['longitude']],
            popup=folium.Popup(f"<b>FIN DU TRAJET</b><br>{end_row['popup_info']}", max_width=300),
            icon=folium.Icon(color='red', icon='stop', prefix='fa')
        ).add_to(self.map)
        
        # Créer le HTML du slider en full screen
        slider_html = f'''
        <div id="timeslider-container" style="position: fixed; bottom: 0; left: 0; right: 0; 
                    height: 120px; background: linear-gradient(to top, rgba(0,0,0,0.8), rgba(0,0,0,0.6)); 
                    z-index: 9999; padding: 20px; color: white;">
            <div style="text-align: center; margin-bottom: 15px;">
                <h3 style="margin: 0; color: white; text-shadow: 2px 2px 4px rgba(0,0,0,0.8);">
                    Slider Temporel - Trajet Chronologique
                </h3>
                <div id="current-time" style="font-size: 24px; color: #FFD700; font-weight: bold; text-shadow: 2px 2px 4px rgba(0,0,0,0.8);">
                    {start_time.strftime('%H:%M:%S')}
                </div>
            </div>
            <input type="range" id="timeslider" min="0" max="{len(time_groups)-1}" value="0" 
                   style="width: 100%; height: 40px; background: transparent; outline: none; cursor: pointer;">
            <div style="display: flex; justify-content: space-between; font-size: 14px; color: #ccc; margin-top: 10px;">
                <span>{start_time.strftime('%H:%M:%S')}</span>
                <span>{end_time.strftime('%H:%M:%S')}</span>
            </div>
        </div>
        '''
        
        self.map.get_root().html.add_child(folium.Element(slider_html))
        
        # Stocker les données pour le JavaScript
        self.time_groups = time_groups
        self.map_data = self.df.to_dict('records')
        
        print("Slider temporel ajouté avec succès")
        return self.map
    
    def _calculate_distance_for_df(self, df):
        """Calculer la distance totale approximative pour un DataFrame donné."""
        from math import radians, cos, sin, asin, sqrt
        
        def haversine(lon1, lat1, lon2, lat2):
            """Calculer la distance entre deux points GPS"""
            lon1, lat1, lon2, lat2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
            dlon = lon2 - lon1
            dlat = lat2 - lat1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * asin(sqrt(a))
            r = 6371  # Rayon de la Terre en km
            return c * r
        
        total_distance = 0
        if len(df) > 1:
            # S'assurer que les coordonnées sont des nombres flottants pour le calcul
            df_numeric = df[['longitude', 'latitude']].apply(pd.to_numeric, errors='coerce').dropna()
            for i in range(1, len(df_numeric)):
                distance = haversine(
                    df_numeric.iloc[i-1]['longitude'], df_numeric.iloc[i-1]['latitude'],
                    df_numeric.iloc[i]['longitude'], df_numeric.iloc[i]['latitude']
                )
                total_distance += distance
        
        return total_distance

    def generate_data_file(self, output_file='data.js'):
        """Générer un fichier JS avec les données du trajet structurées par jour et par trajet."""
        print(f"Génération du fichier de données : {output_file}")
        
        days_data = []
        for day_id, day_df in self.df.groupby('day_id'):
            trips = []
            for trip_id, trip_df in day_df.groupby('trip_id'):
                points = []
                for _, row in trip_df.iterrows():
                    points.append({
                        'lat': row['latitude'],
                        'lon': row['longitude'],
                        'popup': row['popup_info'],
                        'time': row['datetime'].strftime('%H:%M:%S'),
                        'datetime': row['datetime'].isoformat()
                    })
                
                start_time = trip_df['datetime'].min()
                end_time = trip_df['datetime'].max()
                duration = end_time - start_time
                distance_km = self._calculate_distance_for_df(trip_df)
                point_count = len(trip_df)
                
                total_seconds = duration.total_seconds()
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                duration_str = f"{hours}h {minutes}min" if hours > 0 else f"{minutes}min"

                time_groups = []
                current_time = start_time
                group_index = 0
                while current_time <= end_time:
                    time_groups.append({
                        'index': group_index,
                        'time': current_time.strftime('%H:%M:%S'),
                    })
                    group_index += 1
                    current_time += pd.Timedelta(seconds=30)

                trips.append({
                    'id': int(trip_id),
                    'points': points,
                    'time_groups': time_groups,
                    'start_time_full': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'end_time_full': end_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'start_time': start_time.strftime('%H:%M:%S'),
                    'end_time': end_time.strftime('%H:%M:%S'),
                    'center': [trip_df['latitude'].mean(), trip_df['longitude'].mean()],
                    'point_count': point_count,
                    'duration_str': duration_str,
                    'distance_km_str': f"{distance_km:.2f} km"
                })
            
            days_data.append({
                'day_id': day_id,
                'trips': trips
            })

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"window.trajectoryData = {json.dumps({'days': days_data}, indent=4)};")
            
        print("Fichier de données structuré par trajets généré avec succès.")

    def generate_html_and_open(self, output_file='map_visualisation.html'):
        """Générer le fichier HTML et l'ouvrir dans le navigateur"""
        print(f"Génération du fichier HTML : {output_file}")
        
        # ... (le reste de la fonction est supprimé pour se concentrer sur la nouvelle approche)
        pass

    def run_analysis(self):
        """Exécuter l'analyse complète"""
        try:
            # Sélectionner les fichiers
            file_paths = self.select_file()
            if not file_paths:
                print("Aucun fichier sélectionné. Analyse annulée.")
                return
            
            all_dfs = []
            for file_path in file_paths:
                day_id_str = os.path.splitext(os.path.basename(file_path))[0]
                try:
                    # Tenter de parser le nom du fichier comme une date YYYYMMDD
                    day_dt = datetime.strptime(day_id_str, '%Y%m%d')
                    day_id_formatted = day_dt.strftime('%d/%m/%Y')
                except ValueError:
                    # Si le format n'est pas bon, on garde le nom du fichier comme identifiant
                    day_id_formatted = day_id_str
                
                df = self.read_and_parse_data(file_path)
                if df is not None and not df.empty:
                    df['day_id'] = day_id_formatted
                    all_dfs.append(df)
            
            if not all_dfs:
                raise Exception("Aucune donnée valide trouvée dans les fichiers sélectionnés.")

            self.df = pd.concat(all_dfs, ignore_index=True)
            
            # Nettoyer et transformer les données combinées
            self.clean_and_transform_data()
            
            # Générer un seul fichier HTML auto-contenu
            self.generate_standalone_html()

            webbrowser.open(f'file://{os.path.abspath("map_visualisation.html")}')

            print("\n=== ANALYSE TERMINÉE AVEC SUCCÈS ===")
            print(f"Points de géolocalisation analysés : {len(self.df)}")
            print(f"Période couverte : {self.df['datetime'].min()} à {self.df['datetime'].max()}")
            print(f"Distance totale approximative : {self.calculate_total_distance():.2f} km")
            
        except Exception as e:
            print(f"Erreur lors de l'analyse : {e}")
            messagebox.showerror("Erreur", f"Erreur lors de l'analyse : {e}")
    
    def calculate_total_distance(self):
        """Calculer la distance totale approximative du trajet"""
        return self._calculate_distance_for_df(self.df)

    def generate_standalone_html(self, output_file='map_visualisation.html'):
        """Génère un unique fichier HTML auto-contenu avec les données et la logique JS."""
        print(f"Génération du fichier HTML auto-contenu : {output_file}")
        
        # 1. Obtenir les données formatées en JSON
        days_data = []
        for day_id, day_df in self.df.groupby('day_id'):
            trips = []
            for trip_id, trip_df in day_df.groupby('trip_id'):
                points = []
                for _, row in trip_df.iterrows():
                    points.append({
                        'lat': row['latitude'],
                        'lon': row['longitude'],
                        'popup': row['popup_info'],
                        'time': row['datetime'].strftime('%H:%M:%S'),
                        'datetime': row['datetime'].isoformat()
                    })
                
                start_time = trip_df['datetime'].min()
                end_time = trip_df['datetime'].max()
                duration = end_time - start_time
                distance_km = self._calculate_distance_for_df(trip_df)
                point_count = len(trip_df)
                
                total_seconds = duration.total_seconds()
                hours = int(total_seconds // 3600)
                minutes = int((total_seconds % 3600) // 60)
                duration_str = f"{hours}h {minutes}min" if hours > 0 else f"{minutes}min"

                time_groups = []
                current_time = start_time
                group_index = 0
                while current_time <= end_time:
                    time_groups.append({
                        'index': group_index,
                        'time': current_time.strftime('%H:%M:%S'),
                    })
                    group_index += 1
                    current_time += pd.Timedelta(seconds=30)

                trips.append({
                    'id': int(trip_id),
                    'points': points,
                    'time_groups': time_groups,
                    'start_time_full': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'end_time_full': end_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'start_time': start_time.strftime('%H:%M:%S'),
                    'end_time': end_time.strftime('%H:%M:%S'),
                    'center': [trip_df['latitude'].mean(), trip_df['longitude'].mean()],
                    'point_count': point_count,
                    'duration_str': duration_str,
                    'distance_km_str': f"{distance_km:.2f} km"
                })
            days_data.append({'day_id': day_id, 'trips': trips})
        
        json_data = json.dumps({'days': days_data}, indent=4)

        # 2. Intégrer la logique JavaScript directement
        js_logic = f"""
document.addEventListener('DOMContentLoaded', function() {{
    console.log("1. Page chargée, exécution du script embarqué.");
    const data = window.trajectoryData;
    if (!data || !data.days || data.days.length === 0) {{
        console.error("ERREUR : Les données des trajets (window.trajectoryData) sont introuvables ou vides.");
        document.body.innerHTML = "<h1>Aucun trajet détecté.</h1><p>Veuillez vérifier les fichiers de données et leur contenu.</p>";
        return;
    }}
    console.log("2. Données chargées avec succès :", data);

    let currentDayId = null;
    let currentTripId = null;
    let currentMarkers = [];
    let currentPolyline = null;
    let backgroundPolyline = null;
    
    const map = L.map('map').setView([46.2276, 2.2137], 6);
    L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        maxZoom: 19,
        attribution: '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }}).addTo(map);
    console.log("3. Carte Leaflet initialisée.");

    const tripListContainer = document.getElementById('trip-list-container');
    
    if (tripListContainer) {{
        data.days.forEach(day => {{
            const dayHeader = document.createElement('div');
            dayHeader.className = 'day-header';
            dayHeader.textContent = day.day_id; // Utiliser directement la date formatée
            tripListContainer.appendChild(dayHeader);

            const tripList = document.createElement('ul');
            day.trips.forEach(trip => {{
                const li = document.createElement('li');
                const button = document.createElement('button');
                button.innerHTML = `
                    <div style="font-weight: bold; font-size: 1.1em; margin-bottom: 5px;">Trajet #${{trip.id + 1}}</div>
                    <div style="font-size: 0.8em; color: #6c757d;">${{trip.start_time_full.split(' ')[1]}} - ${{trip.end_time_full.split(' ')[1]}}</div>
                    <div style="font-size: 0.9em; margin-top: 8px;">
                        <span>📍 ${{trip.point_count}} points</span><br>
                        <span>📏 ${{trip.distance_km_str}}</span> | <span>⏱️ ${{trip.duration_str}}</span>
                    </div>
                `;
                button.onclick = () => {{
                    selectTrip(day.day_id, trip.id);
                    document.querySelectorAll('#trip-list-container button').forEach(b => b.classList.remove('active'));
                    button.classList.add('active');
                }};
                li.appendChild(button);
                tripList.appendChild(li);
            }});
            tripListContainer.appendChild(tripList);
        }});
        console.log("4. Sidebar remplie avec tous les trajets.");
    }} else {{
        console.error("ERREUR : Le conteneur de la sidebar ('trip-list-container') est introuvable.");
    }}
    
    function selectTrip(dayId, tripId) {{
        console.log(`5. Sélection du trajet : Jour ${{dayId}}, Trajet ${{tripId}}`);
        currentDayId = dayId;
        currentTripId = tripId;
        const dayData = data.days.find(d => d.day_id === dayId);
        const tripData = dayData.trips.find(t => t.id === tripId);
        
        if (!tripData) {{
            console.error(`ERREUR : Données introuvables pour le trajet ${{tripId}} du jour ${{dayId}}.`);
            return;
        }}

        currentMarkers.forEach(marker => map.removeLayer(marker));
        currentMarkers = [];
        if (currentPolyline) map.removeLayer(currentPolyline);
        if (backgroundPolyline) map.removeLayer(backgroundPolyline);

        map.flyTo(tripData.center, 13);
        const allCoords = tripData.points.map(p => [p.lat, p.lon]);
        backgroundPolyline = L.polyline(allCoords, {{ color: 'gray', weight: 3, opacity: 0.5, dashArray: '5, 5' }}).addTo(map);
        
        updateSliderUI(tripData);
        updateMapDisplay(0);
    }}
    
    function updateSliderUI(tripData) {{
        const sliderContainer = document.getElementById('timeslider-container');
        sliderContainer.innerHTML = '';
        sliderContainer.style.display = tripData ? 'block' : 'none';
        if (!tripData) return;

        sliderContainer.style.cssText = `
            position: fixed; bottom: 20px; left: calc(300px + 5%);
            width: calc(90% - 300px); max-width: 1200px;
            background-color: rgba(255, 255, 255, 0.9); z-index: 1000;
            padding: 20px; color: #333; border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2); backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.3);
        `;
        
        sliderContainer.innerHTML = `
            <div style="text-align: center; margin-bottom: 15px;">
                <h3 style="margin: 0; color: #1a1a1a; font-weight: 700; font-size: 1.1rem;">
                    CONTRÔLE CHRONOLOGIQUE (Trajet #${{tripData.id + 1}})
                </h3>
                <div id="current-time" style="font-size: 1.8rem; color: #007bff; font-weight: bold;">
                    ${{tripData.start_time}}
                </div>
            </div>
            <input type="range" id="timeslider" min="0" max="${{tripData.time_groups.length - 1}}" value="0" 
                   class="form-range" style="width: 100%; height: 1.5rem; cursor: pointer;">
            <div style="display: flex; justify-content: space-between; font-size: 0.9rem; color: #6c757d; margin-top: 5px;">
                <span>${{tripData.start_time}}</span>
                <span>${{tripData.end_time}}</span>
            </div>
        `;
        const slider = document.getElementById('timeslider');
        slider.addEventListener('input', function() {{
            updateMapDisplay(parseInt(this.value));
        }});
    }}

    function updateMapDisplay(sliderValue) {{
        const dayData = data.days.find(d => d.day_id === currentDayId);
        if (!dayData) return;
        const tripData = dayData.trips.find(t => t.id === currentTripId);
        if (!tripData) return;

        currentMarkers.forEach(marker => map.removeLayer(marker));
        currentMarkers = [];
        if (currentPolyline) map.removeLayer(currentPolyline);
        
        const targetTimeStr = tripData.time_groups[sliderValue].time;
        const targetTime = new Date(`1970-01-01T${{targetTimeStr}}Z`).getTime();
        
        const visiblePoints = tripData.points.filter(p => new Date(`1970-01-01T${{p.time}}Z`).getTime() <= targetTime);
        
        let closestPoint = null;
        let minTimeDiff = Infinity;
        visiblePoints.forEach(point => {{
            const pointTime = new Date(`1970-01-01T${{point.time}}Z`).getTime();
            const timeDiff = Math.abs(pointTime - targetTime);
            if (timeDiff < minTimeDiff) {{
                minTimeDiff = timeDiff;
                closestPoint = point;
            }}
        }});

        const greenPointsCoords = visiblePoints.map(p => [p.lat, p.lon]);

        visiblePoints.forEach(point => {{
            const isHighlighted = (closestPoint && point.datetime === closestPoint.datetime);
            const marker = L.circleMarker([point.lat, point.lon], {{
                radius: isHighlighted ? 12 : 5,
                color: isHighlighted ? 'red' : 'green',
                fillColor: isHighlighted ? 'red' : 'green',
                fillOpacity: 1.0,
                weight: isHighlighted ? 4 : 2
            }}).bindPopup(point.popup);
            marker.addTo(map);
            currentMarkers.push(marker);
        }});

        if (greenPointsCoords.length > 1) {{
            currentPolyline = L.polyline(greenPointsCoords, {{ color: 'green', weight: 4, opacity: 0.8 }}).addTo(map);
        }}
        
        document.getElementById('current-time').textContent = targetTimeStr;
    }}
    
    updateSliderUI(null);
    
    if (data.days.length > 0 && data.days[0].trips.length > 0) {{
        console.log("10. Sélection automatique du premier trajet...");
        document.querySelector('#trip-list-container button').click();
    }}
}});
"""

        # 3. Construire le HTML final
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Visualisation du trajet</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap">
    <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
    <style>
        body, html {{ 
            margin: 0; 
            padding: 0; 
            height: 100%; 
            overflow: hidden; 
            font-family: 'Roboto', sans-serif;
        }}
        #map {{ height: 100vh; width: calc(100vw - 300px); }}
        #sidebar {{
            position: fixed; top: 0; left: 0; height: 100%;
            width: 300px; background-color: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
            border-right: 1px solid rgba(0,0,0,0.1); box-shadow: 2px 0 10px rgba(0,0,0,0.1);
            z-index: 1000; padding: 20px; overflow-y: auto;
        }}
        #sidebar h2 {{
            margin-top: 0; color: #333; border-bottom: 2px solid #dee2e6;
            padding-bottom: 10px;
        }}
        #sidebar .day-header {{
            font-size: 1.2em; font-weight: bold; color: #007bff;
            margin-top: 20px; margin-bottom: 10px;
            border-bottom: 1px solid #e9ecef; padding-bottom: 5px;
        }}
        #sidebar ul {{ list-style: none; padding: 0; margin: 0; }}
        #sidebar li button {{
            width: 100%; padding: 12px 15px; margin-bottom: 8px;
            text-align: left; background-color: #f8f9fa; color: #333;
            border: 1px solid #dee2e6; border-radius: 8px;
            cursor: pointer; transition: all 0.2s ease-in-out;
            line-height: 1.4;
        }}
        #sidebar li button:hover {{ background-color: #e9ecef; border-color: #adb5bd; }}
        #sidebar li button.active {{
            background-color: #007bff; color: white; border-color: #0056b3;
            transform: translateY(-2px); box-shadow: 0 4px 10px rgba(0, 123, 255, 0.4);
        }}
        #sidebar li button.active div,
        #sidebar li button.active span,
        #sidebar li button.active small {{ color: white !important; }}
    </style>
</head>
<body>
    <div id="sidebar">
        <h2>Trajets</h2>
        <div id="trip-list-container"></div>
    </div>
    <div id="map" style="margin-left: 300px;"></div>
    <div id="timeslider-container"></div>
    
    <script>
        window.trajectoryData = {json_data};
    </script>
    <script>
        {js_logic}
    </script>
</body>
</html>
"""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print("Fichier HTML généré avec succès.")

def main():
    """Fonction principale"""
    print("=== ANALYSEUR FORENSIQUE DE DONNÉES DE GÉOLOCALISATION ===")
    print("Développé pour l'analyse de fichiers .dat de dashcam")
    print()
    
    analyzer = DashcamAnalyzer()
    analyzer.run_analysis()


if __name__ == "__main__":
    main()
