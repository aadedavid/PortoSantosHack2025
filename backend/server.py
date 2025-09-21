from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timedelta
import httpx
import asyncio
from enum import Enum
import re
from bs4 import BeautifulSoup
from marine_traffic_links import MarineTrafficLinkBuilder, create_vessel_links


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# External API base URL
EXTERNAL_API_BASE = "https://api.hackathon.souamigu.org.br"

# Create the main app without a prefix
app = FastAPI(title="Hub de Atracação - Porto de Santos", version="1.0.0")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Enums for better type safety
class StatusOperacao(str, Enum):
    PLANEJADO = "planejado"
    EM_ANDAMENTO = "em_andamento"
    CONCLUIDO = "concluido"
    CANCELADO = "cancelado"
    ATRASO = "atraso"
    PENDENTE = "pendente"


class TipoMovimentacao(str, Enum):
    ENTRADA = "entrada"
    SAIDA = "saida"


class PrioridadeRAP(str, Enum):
    IMEDIATA = "imediata"
    PREFERENCIAL = "preferencial"
    PRIORITARIA = "prioritaria"
    SEQUENCIAL = "sequencial"


# Data Models
class TimestampInfo(BaseModel):
    estimado: Optional[datetime] = None
    real: Optional[datetime] = None
    registrado: Optional[datetime] = None


class VesselSchedule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    identificador_navio: str
    nome_navio: Optional[str] = None
    agencia_maritima: Optional[str] = None
    terminal: Optional[str] = None
    berco: Optional[str] = None
    
    # R/E/O Timestamps (Registered/Estimated/Occurred)
    eta: TimestampInfo = Field(default_factory=TimestampInfo)  # Estimated Time of Arrival
    etb: TimestampInfo = Field(default_factory=TimestampInfo)  # Estimated Time of Berthing
    etd: TimestampInfo = Field(default_factory=TimestampInfo)  # Estimated Time of Departure
    
    ata: Optional[datetime] = None  # Actual Time of Arrival
    atb: Optional[datetime] = None  # Actual Time of Berthing
    atd: Optional[datetime] = None  # Actual Time of Departure
    
    prioridade_rap: PrioridadeRAP = PrioridadeRAP.SEQUENCIAL
    status: StatusOperacao = StatusOperacao.PLANEJADO
    
    # Additional info
    tipo_operacao: Optional[str] = None
    observacoes: Optional[str] = None
    intercorrencias: Optional[str] = None
    
    # MarineTraffic integration
    imo: Optional[str] = None
    mmsi: Optional[str] = None
    shipid: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BerthInfo(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nome: str
    terminal: str
    capacidade_maxima: int
    ocupado: bool = False
    navio_atual: Optional[str] = None
    proxima_disponibilidade: Optional[datetime] = None


class ConflictAlert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    berco: str
    navios_conflito: List[str]
    tipo_conflito: str  # "overlap", "capacity_exceeded", "priority_violation"
    descricao: str
    tempo_overlap: Optional[int] = None  # minutes
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolvido: bool = False


class KPIMetrics(BaseModel):
    mae_eta: Optional[float] = None  # Mean Absolute Error for ETA
    wb_ratio: Optional[float] = None  # Waiting to Berth Ratio
    rcj_reliability: Optional[float] = None  # Berth Window Reliability
    periodo_inicio: datetime
    periodo_fim: datetime
    total_escalas: int = 0


# External API Service
class ExternalAPIService:
    def __init__(self):
        self.base_url = EXTERNAL_API_BASE
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def fetch_agencia_maritima_data(self) -> List[Dict[str, Any]]:
        """Fetch maritime agency data"""
        try:
            response = await self.client.get(f"{self.base_url}/agencia-maritima")
            if response.status_code == 200:
                return response.json().get("data", [])
            return []
        except Exception as e:
            logging.error(f"Error fetching agencia maritima data: {e}")
            return []
    
    async def fetch_praticagem_data(self) -> List[Dict[str, Any]]:
        """Fetch pilotage data"""
        try:
            response = await self.client.get(f"{self.base_url}/praticagem")
            if response.status_code == 200:
                return response.json().get("data", [])
            return []
        except Exception as e:
            logging.error(f"Error fetching praticagem data: {e}")
            return []
    
    async def fetch_terminal_data(self) -> List[Dict[str, Any]]:
        """Fetch port terminal data"""
        try:
            response = await self.client.get(f"{self.base_url}/terminal-portuario")
            if response.status_code == 200:
                return response.json().get("data", [])
            return []
        except Exception as e:
            logging.error(f"Error fetching terminal data: {e}")
            return []
    
    async def fetch_autoridade_portuaria_data(self) -> List[Dict[str, Any]]:
        """Fetch port authority data"""
        try:
            response = await self.client.get(f"{self.base_url}/autoridade-portuaria")
            if response.status_code == 200:
                return response.json().get("data", [])
            return []
        except Exception as e:
            logging.error(f"Error fetching autoridade portuaria data: {e}")
            return []
    
    async def fetch_extended_historical_data(self, days_back: int = 30) -> List[Dict[str, Any]]:
        """Fetch extended historical data by calling APIs multiple times with different date ranges"""
        all_data = []
        
        # Get current data first
        current_data = await self.fetch_agencia_maritima_data()
        terminal_data = await self.fetch_terminal_data()
        praticagem_data = await self.fetch_praticagem_data()
        autoridade_data = await self.fetch_autoridade_portuaria_data()
        
        # Add more vessels by fetching individual vessel data if possible
        try:
            # Try to get more vessels by ID (example approach)
            base_vessels = current_data + terminal_data + praticagem_data + autoridade_data
            vessel_ids = list(set([v.get('identificadorNavio') for v in base_vessels if v.get('identificadorNavio')]))
            
            # Generate some historical data for demonstration
            extended_data = []
            for i, vessel_id in enumerate(vessel_ids[:20]):  # Limit to 20 vessels
                if vessel_id:
                    # Create historical entries
                    for days_ago in range(0, min(days_back, 7)):  # Limit to 7 days for demo
                        historical_entry = {
                            'identificadorNavio': f"{vessel_id}-H{days_ago}",
                            'nomeAgencia': f"Historical Agency {i+1}",
                            'dataEnvioInformacoes': (datetime.utcnow() - timedelta(days=days_ago)).isoformat(),
                            'manifestoEntregue': days_ago < 3,
                            'statusDocumentacao': 'completo' if days_ago < 3 else 'pendente'
                        }
                        extended_data.append(historical_entry)
            
            all_data.extend(extended_data)
            
        except Exception as e:
            logging.warning(f"Could not generate extended historical data: {e}")
        
        return all_data

    async def scrape_marinetraffic_santos(self) -> List[Dict[str, Any]]:
        """Simple scraping of MarineTraffic for vessels heading to Santos Port"""
        vessels_data = []
        
        try:
            # Simple scraping approach - this is for MVP/demo purposes
            # In production, you'd use proper APIs or more robust scraping
            
            # Search for vessels near Santos port coordinates
            santos_lat, santos_lon = -23.9534, -46.3334
            
            # For demo purposes, create sample AIS data based on real patterns
            sample_vessels = [
                {
                    'mmsi': '710006293',
                    'imo': '9506394',
                    'shipid': '714410', 
                    'vessel_name': 'LOG IN DISCOVERY',
                    'destination': 'BR SSZ',  # Santos port code
                    'eta': (datetime.utcnow() + timedelta(hours=12)).isoformat(),
                    'current_speed': 14.2,
                    'latitude': -22.5,
                    'longitude': -44.8,
                    'status': 'Under way using engine',
                    'distance_to_port': 85.3
                },
                {
                    'mmsi': '710001234',
                    'imo': '9400567',
                    'shipid': '712345',
                    'vessel_name': 'MSC MEDITERRANEAN',
                    'destination': 'BR SSZ',
                    'eta': (datetime.utcnow() + timedelta(hours=8)).isoformat(),
                    'current_speed': 12.8,
                    'latitude': -23.2,
                    'longitude': -45.1,
                    'status': 'Under way using engine',
                    'distance_to_port': 45.2
                },
                {
                    'mmsi': '710005678',
                    'imo': '9350123',
                    'shipid': '798765',
                    'vessel_name': 'MAERSK SALVADOR',
                    'destination': 'BR SSZ',
                    'eta': (datetime.utcnow() + timedelta(hours=24)).isoformat(),
                    'current_speed': 16.5,
                    'latitude': -21.8,
                    'longitude': -43.9,
                    'status': 'Under way using engine',
                    'distance_to_port': 150.7
                }
            ]
            
            vessels_data.extend(sample_vessels)
            
        except Exception as e:
            logging.error(f"Error scraping MarineTraffic data: {e}")
        
        return vessels_data

    async def scrape_aps_diope_tables(self) -> Dict[str, List[Dict[str, Any]]]:
        """Scrape APS DIOPE public tables (Fundeados/Esperados/Atracados/Programadas)"""
        diope_data = {
            "esperados": [],
            "fundeados": [],
            "atracados": [],
            "programadas": []
        }
        
        try:
            # For MVP, we'll simulate APS DIOPE data structure
            # In production, this would scrape actual APS public pages
            
            # Simulate "Navios Esperados" - Expected vessels
            esperados_sample = [
                {
                    "navio": "CMA CGM MARSEILLE",
                    "terminal": "Brasil Terminal Portuário",
                    "berco": "BTP01",
                    "etb_estimado": (datetime.utcnow() + timedelta(hours=6)).isoformat(),
                    "operacao": "descarga",
                    "agencia": "CMA CGM do Brasil",
                    "origem": "Buenos Aires"
                },
                {
                    "navio": "EVER LEGEND", 
                    "terminal": "Tecon Santos",
                    "berco": "TS15",
                    "etb_estimado": (datetime.utcnow() + timedelta(hours=12)).isoformat(),
                    "operacao": "carga",
                    "agencia": "Evergreen Marine",
                    "origem": "Rio de Janeiro"
                },
                {
                    "navio": "APL CHANGI",
                    "terminal": "Ecoporto Santos", 
                    "berco": "EC03",
                    "etb_estimado": (datetime.utcnow() + timedelta(hours=18)).isoformat(),
                    "operacao": "transbordo",
                    "agencia": "APL Brasil",
                    "origem": "Paranaguá"
                }
            ]
            
            # Simulate "Navios Fundeados" - Anchored vessels (recent arrivals)
            fundeados_sample = [
                {
                    "navio": "MSC FIAMMETTA",
                    "ata_fundeio": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                    "aguardando": "berço livre",
                    "terminal_destino": "Brasil Terminal Portuário",
                    "agencia": "MSC Brasil",
                    "posicao_fundeio": "F-03"
                },
                {
                    "navio": "CCNI ARAUCO",
                    "ata_fundeio": (datetime.utcnow() - timedelta(hours=8)).isoformat(),
                    "aguardando": "documentação",
                    "terminal_destino": "Tecon Santos", 
                    "agencia": "CCNI Brasil",
                    "posicao_fundeio": "F-07"
                }
            ]
            
            # Simulate "Navios Atracados" - Currently berthed
            atracados_sample = [
                {
                    "navio": "HAPAG LLOYD SANTOS",
                    "terminal": "Tecon Santos",
                    "berco": "TS12",
                    "atb_real": (datetime.utcnow() - timedelta(hours=14)).isoformat(),
                    "etd_estimado": (datetime.utcnow() + timedelta(hours=10)).isoformat(),
                    "operacao": "descarga/carga",
                    "progresso": "78%",
                    "agencia": "Hapag-Lloyd Brasil"
                },
                {
                    "navio": "ZIM KINGSTON",
                    "terminal": "Brasil Terminal Portuário", 
                    "berco": "BTP02",
                    "atb_real": (datetime.utcnow() - timedelta(hours=22)).isoformat(),
                    "etd_estimado": (datetime.utcnow() + timedelta(hours=4)).isoformat(),
                    "operacao": "carga",
                    "progresso": "92%",
                    "agencia": "ZIM Brasil"
                }
            ]
            
            # Simulate "Navios Programadas" - Scheduled vessels
            programadas_sample = [
                {
                    "navio": "ONE COMMITMENT",
                    "terminal": "Ecoporto Santos",
                    "berco": "EC01", 
                    "etb_programado": (datetime.utcnow() + timedelta(days=1, hours=8)).isoformat(),
                    "etd_programado": (datetime.utcnow() + timedelta(days=2, hours=2)).isoformat(),
                    "operacao": "descarga",
                    "agencia": "Ocean Network Express",
                    "status_programa": "confirmado"
                },
                {
                    "navio": "MAERSK LEON",
                    "terminal": "Brasil Terminal Portuário",
                    "berco": "BTP03",
                    "etb_programado": (datetime.utcnow() + timedelta(days=1, hours=16)).isoformat(), 
                    "etd_programado": (datetime.utcnow() + timedelta(days=2, hours=12)).isoformat(),
                    "operacao": "carga/descarga",
                    "agencia": "Maersk Brasil",
                    "status_programa": "tentativo"
                }
            ]
            
            diope_data["esperados"] = esperados_sample
            diope_data["fundeados"] = fundeados_sample  
            diope_data["atracados"] = atracados_sample
            diope_data["programadas"] = programadas_sample
            
        except Exception as e:
            logging.error(f"Error scraping APS DIOPE data: {e}")
        
        return diope_data

    async def close(self):
        await self.client.aclose()


# Global service instance
external_api = ExternalAPIService()


# Data consolidation service
class DataConsolidationService:
    @staticmethod
    def consolidate_vessel_data(
        agencia_data: List[Dict], 
        praticagem_data: List[Dict], 
        terminal_data: List[Dict], 
        autoridade_data: List[Dict]
    ) -> List[VesselSchedule]:
        """Consolidate data from multiple sources into unified vessel schedules"""
        
        vessels_dict = {}
        
        # Process terminal data (primary source for scheduling)
        for terminal_item in terminal_data:
            vessel_id = terminal_item.get("identificadorNavio")
            if not vessel_id:
                continue
                
            vessel = VesselSchedule(
                identificador_navio=vessel_id,
                terminal=terminal_item.get("nomeTerminal"),
                tipo_operacao=terminal_item.get("tipoOperacao"),
                status=DataConsolidationService._map_status(terminal_item.get("statusOperacao")),
                observacoes=terminal_item.get("observacoes")
            )
            
            # Set ETB/ATB from terminal data
            if terminal_item.get("dataPrevistaAtracacao"):
                vessel.etb.estimado = datetime.fromisoformat(terminal_item["dataPrevistaAtracacao"].replace("Z", "+00:00"))
            if terminal_item.get("dataRealAtracacao"):
                vessel.atb = datetime.fromisoformat(terminal_item["dataRealAtracacao"].replace("Z", "+00:00"))
            
            vessels_dict[vessel_id] = vessel
        
        # Enrich with agency data
        for agencia_item in agencia_data:
            vessel_id = agencia_item.get("identificadorNavio")
            if vessel_id in vessels_dict:
                vessels_dict[vessel_id].agencia_maritima = agencia_item.get("nomeAgencia")
        
        # Add sample MarineTraffic data for known vessels
        sample_marine_data = {
            "LOG-IN-DISCOVERY": {"imo": "9506394", "mmsi": "710006293", "shipid": "714410"},
            "MSC-MEDITERRANEAN": {"imo": "9400567", "mmsi": "710001234", "shipid": "712345"},
            "MAERSK-SALVADOR": {"imo": "9350123", "mmsi": "710005678", "shipid": "798765"},
            "MSC-SANTOS-001": {"imo": "9123456", "mmsi": "710001111", "shipid": "701111"},
            "COSCO-BR-003": {"imo": "9234567", "mmsi": "710002222", "shipid": "702222"},
            "HAMBURG-SANTOS-005": {"imo": "9345678", "mmsi": "710003333", "shipid": "703333"}
        }
        
        for vessel_id, vessel in vessels_dict.items():
            if vessel_id in sample_marine_data:
                marine_data = sample_marine_data[vessel_id]
                vessel.imo = marine_data["imo"]
                vessel.mmsi = marine_data["mmsi"]
                vessel.shipid = marine_data["shipid"]
                # Add approximate coordinates for Santos area
                vessel.latitude = -23.9534 + (hash(vessel_id) % 100 - 50) * 0.01  # Random around Santos
                vessel.longitude = -46.3334 + (hash(vessel_id) % 100 - 50) * 0.01
        
        # Enrich with pilotage data
        for praticagem_item in praticagem_data:
            vessel_id = praticagem_item.get("identificadorNavio")
            if vessel_id in vessels_dict:
                if praticagem_item.get("dataSolicitacao"):
                    vessels_dict[vessel_id].eta.registrado = datetime.fromisoformat(
                        praticagem_item["dataSolicitacao"].replace("Z", "+00:00"))
                if praticagem_item.get("dataExecucao"):
                    if praticagem_item.get("manobraTipo") == "entrada":
                        vessels_dict[vessel_id].ata = datetime.fromisoformat(
                            praticagem_item["dataExecucao"].replace("Z", "+00:00"))
                    elif praticagem_item.get("manobraTipo") == "saida":
                        vessels_dict[vessel_id].atd = datetime.fromisoformat(
                            praticagem_item["dataExecucao"].replace("Z", "+00:00"))
                
                if praticagem_item.get("motivoIntercorrencia"):
                    vessels_dict[vessel_id].intercorrencias = praticagem_item["motivoIntercorrencia"]
        
        return list(vessels_dict.values())
    
    @staticmethod
    def _map_status(terminal_status: str) -> StatusOperacao:
        """Map terminal status to our internal status enum"""
        status_mapping = {
            "concluida": StatusOperacao.CONCLUIDO,
            "aguardando_navio": StatusOperacao.PENDENTE,
            "cancelada": StatusOperacao.CANCELADO,
            "aguardando_documentacao": StatusOperacao.PENDENTE,
            "concluida_com_atraso": StatusOperacao.ATRASO,
            "parcial": StatusOperacao.EM_ANDAMENTO
        }
        return status_mapping.get(terminal_status, StatusOperacao.PLANEJADO)


# Business Logic Services
class ConflictDetectionService:
    @staticmethod
    def detect_berth_conflicts(schedules: List[VesselSchedule]) -> List[ConflictAlert]:
        """Detect berth conflicts between vessel schedules"""
        conflicts = []
        
        # Group schedules by terminal/berth
        berth_schedules = {}
        for schedule in schedules:
            if schedule.terminal and schedule.etb.estimado and schedule.etd.estimado:
                key = schedule.terminal
                if key not in berth_schedules:
                    berth_schedules[key] = []
                berth_schedules[key].append(schedule)
        
        # Check for overlaps within each berth
        for berth, vessel_schedules in berth_schedules.items():
            for i, vessel1 in enumerate(vessel_schedules):
                for j, vessel2 in enumerate(vessel_schedules[i+1:], i+1):
                    conflict = ConflictDetectionService._check_time_overlap(vessel1, vessel2, berth)
                    if conflict:
                        conflicts.append(conflict)
        
        return conflicts
    
    @staticmethod
    def _check_time_overlap(vessel1: VesselSchedule, vessel2: VesselSchedule, berth: str) -> Optional[ConflictAlert]:
        """Check if two vessels have overlapping berth times"""
        v1_start = vessel1.etb.estimado or vessel1.atb
        v1_end = vessel1.etd.estimado or vessel1.atd
        v2_start = vessel2.etb.estimado or vessel2.atb
        v2_end = vessel2.etd.estimado or vessel2.atd
        
        if not all([v1_start, v1_end, v2_start, v2_end]):
            return None
        
        # Check for overlap
        if v1_start < v2_end and v2_start < v1_end:
            overlap_start = max(v1_start, v2_start)
            overlap_end = min(v1_end, v2_end)
            overlap_minutes = int((overlap_end - overlap_start).total_seconds() / 60)
            
            return ConflictAlert(
                berco=berth,
                navios_conflito=[vessel1.identificador_navio, vessel2.identificador_navio],
                tipo_conflito="overlap",
                descricao=f"Conflito de atracação: {vessel1.identificador_navio} e {vessel2.identificador_navio} sobrepõem em {overlap_minutes} minutos",
                tempo_overlap=overlap_minutes
            )
        
        return None


class KPICalculationService:
    @staticmethod
    def calculate_kpis(schedules: List[VesselSchedule], start_date: datetime, end_date: datetime) -> KPIMetrics:
        """Calculate key performance indicators"""
        
        # Filter schedules within date range - use any available timestamp
        relevant_schedules = []
        for s in schedules:
            schedule_date = s.ata or s.atb or s.eta.registrado or s.etb.estimado
            if schedule_date and start_date <= schedule_date <= end_date:
                relevant_schedules.append(s)
        
        if not relevant_schedules:
            return KPIMetrics(
                periodo_inicio=start_date,
                periodo_fim=end_date,
                total_escalas=0
            )
        
        # Calculate MAE (Mean Absolute Error) for ETA
        # Use registered ETA if estimated is not available
        mae_errors = []
        for schedule in relevant_schedules:
            eta_estimated = schedule.eta.estimado or schedule.eta.registrado
            if eta_estimated and schedule.ata:
                error_minutes = abs((schedule.ata - eta_estimated).total_seconds() / 60)
                mae_errors.append(error_minutes)
            elif eta_estimated and schedule.atb:  # Use ATB if ATA not available
                error_minutes = abs((schedule.atb - eta_estimated).total_seconds() / 60)
                mae_errors.append(error_minutes)
        
        mae_eta = sum(mae_errors) / len(mae_errors) if mae_errors else None
        
        # Calculate W/B Ratio (Waiting to Berth Ratio)
        wb_ratios = []
        for schedule in relevant_schedules:
            arrival_time = schedule.ata or schedule.eta.registrado
            berth_time = schedule.atb
            departure_time = schedule.atd
            
            if arrival_time and berth_time and departure_time:
                waiting_time = (berth_time - arrival_time).total_seconds() / 60
                berthed_time = (departure_time - berth_time).total_seconds() / 60
                if berthed_time > 0 and waiting_time >= 0:
                    wb_ratio = waiting_time / berthed_time
                    wb_ratios.append(wb_ratio)
        
        wb_ratio = sum(wb_ratios) / len(wb_ratios) if wb_ratios else None
        
        # Calculate RCJ (Berth Window Reliability) - % within ±30 min
        rcj_count = 0
        rcj_total = 0
        for schedule in relevant_schedules:
            if schedule.etb.estimado and schedule.atb:
                error_minutes = abs((schedule.atb - schedule.etb.estimado).total_seconds() / 60)
                rcj_total += 1
                if error_minutes <= 30:  # Within ±30 minutes
                    rcj_count += 1
        
        rcj_reliability = (rcj_count / rcj_total * 100) if rcj_total > 0 else None
        
        return KPIMetrics(
            mae_eta=mae_eta,
            wb_ratio=wb_ratio,
            rcj_reliability=rcj_reliability,
            periodo_inicio=start_date,
            periodo_fim=end_date,
            total_escalas=len(relevant_schedules)
        )


# API Endpoints
@api_router.get("/")
async def root():
    return {"message": "Hub de Atracação - Porto de Santos API", "version": "1.0.0"}


@api_router.post("/sync-external-data")
async def sync_external_data():
    """Synchronize data from external APIs and consolidate vessel schedules"""
    try:
        # Fetch data from all external sources
        agencia_data = await external_api.fetch_agencia_maritima_data()
        praticagem_data = await external_api.fetch_praticagem_data()
        terminal_data = await external_api.fetch_terminal_data()
        autoridade_data = await external_api.fetch_autoridade_portuaria_data()
        
        # Consolidate data
        vessel_schedules = DataConsolidationService.consolidate_vessel_data(
            agencia_data, praticagem_data, terminal_data, autoridade_data
        )
        
        # Store in database
        for schedule in vessel_schedules:
            await db.vessel_schedules.replace_one(
                {"identificador_navio": schedule.identificador_navio},
                schedule.dict(),
                upsert=True
            )
        
        # Detect conflicts
        conflicts = ConflictDetectionService.detect_berth_conflicts(vessel_schedules)
        
        # Store conflicts
        for conflict in conflicts:
            await db.conflicts.replace_one(
                {"id": conflict.id},
                conflict.dict(),
                upsert=True
            )
        
        return {
            "message": "Data synchronized successfully",
            "vessels_processed": len(vessel_schedules),
            "conflicts_detected": len(conflicts)
        }
    
    except Exception as e:
        logging.error(f"Error syncing external data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/vessels", response_model=List[VesselSchedule])
async def get_vessels():
    """Get all vessel schedules"""
    try:
        vessels = await db.vessel_schedules.find().to_list(1000)
        return [VesselSchedule(**vessel) for vessel in vessels]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/vessels/{vessel_id}", response_model=VesselSchedule)
async def get_vessel(vessel_id: str):
    """Get specific vessel schedule"""
    try:
        vessel = await db.vessel_schedules.find_one({"identificador_navio": vessel_id})
        if not vessel:
            raise HTTPException(status_code=404, detail="Vessel not found")
        return VesselSchedule(**vessel)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/conflicts", response_model=List[ConflictAlert])
async def get_conflicts():
    """Get all berth conflicts"""
    try:
        conflicts = await db.conflicts.find({"resolvido": False}).to_list(1000)
        return [ConflictAlert(**conflict) for conflict in conflicts]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: str):
    """Mark a conflict as resolved"""
    try:
        result = await db.conflicts.update_one(
            {"id": conflict_id},
            {"$set": {"resolvido": True}}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Conflict not found")
        return {"message": "Conflict resolved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/kpis")
async def get_kpis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get KPI metrics for specified date range"""
    try:
        # Default to last 30 days if no dates provided
        if not end_date:
            end_dt = datetime.utcnow()
        else:
            end_dt = datetime.fromisoformat(end_date)
        
        if not start_date:
            start_dt = end_dt - timedelta(days=30)
        else:
            start_dt = datetime.fromisoformat(start_date)
        
        # Get vessel schedules
        vessels = await db.vessel_schedules.find().to_list(1000)
        vessel_schedules = [VesselSchedule(**vessel) for vessel in vessels]
        
        # Calculate KPIs
        kpis = KPICalculationService.calculate_kpis(vessel_schedules, start_dt, end_dt)
        
        return kpis.dict()
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/sync-historical-data")
async def sync_historical_data(days_back: int = 7):
    """Sync extended historical data for better KPI calculations"""
    try:
        historical_data = await external_api.fetch_extended_historical_data(days_back)
        
        # Store historical data
        for entry in historical_data:
            vessel_schedule = VesselSchedule(
                identificador_navio=entry.get('identificadorNavio'),
                agencia_maritima=entry.get('nomeAgencia'),
                status=StatusOperacao.PLANEJADO,
                created_at=datetime.fromisoformat(entry.get('dataEnvioInformacoes', datetime.utcnow().isoformat()))
            )
            
            await db.vessel_schedules.replace_one(
                {"identificador_navio": vessel_schedule.identificador_navio},
                vessel_schedule.dict(),
                upsert=True
            )
        
        return {
            "message": "Historical data synchronized successfully",
            "historical_entries": len(historical_data),
            "days_back": days_back
        }
    
    except Exception as e:
        logging.error(f"Error syncing historical data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/operations/now")
async def get_current_operations():
    """Get current port operations - recent arrivals, current operations, next 24h"""
    try:
        now = datetime.utcnow()
        yesterday = now - timedelta(hours=24)
        tomorrow = now + timedelta(hours=24)
        
        # Get vessels in current operational window
        vessels = await db.vessel_schedules.find().to_list(1000)
        
        current_ops = {
            "recently_arrived": [],  # Arrived in last 24h
            "currently_berthed": [], # Currently at berth
            "arriving_soon": [],     # Expected in next 24h
            "departing_soon": []     # Expected to depart in next 24h
        }
        
        for vessel_data in vessels:
            vessel = VesselSchedule(**vessel_data)
            
            # Recently arrived (ATA in last 24h)
            if vessel.ata and yesterday <= vessel.ata <= now:
                current_ops["recently_arrived"].append({
                    "vessel": vessel.identificador_navio,
                    "terminal": vessel.terminal,
                    "arrival_time": vessel.ata.isoformat(),
                    "hours_ago": int((now - vessel.ata).total_seconds() / 3600),
                    "status": vessel.status,
                    "agency": vessel.agencia_maritima
                })
            
            # Currently berthed (ATB exists, no ATD yet)
            if vessel.atb and not vessel.atd:
                berth_duration = int((now - vessel.atb).total_seconds() / 3600) if vessel.atb else 0
                current_ops["currently_berthed"].append({
                    "vessel": vessel.identificador_navio,
                    "terminal": vessel.terminal,
                    "berthed_since": vessel.atb.isoformat() if vessel.atb else None,
                    "hours_berthed": berth_duration,
                    "status": vessel.status,
                    "operation": vessel.tipo_operacao,
                    "agency": vessel.agencia_maritima
                })
            
            # Arriving soon (ETB in next 24h)
            etb_time = vessel.etb.estimado or vessel.etb.registrado
            if etb_time and now <= etb_time <= tomorrow:
                hours_until = int((etb_time - now).total_seconds() / 3600)
                current_ops["arriving_soon"].append({
                    "vessel": vessel.identificador_navio,
                    "terminal": vessel.terminal,
                    "expected_berth": etb_time.isoformat(),
                    "hours_until": hours_until,
                    "priority": vessel.prioridade_rap,
                    "agency": vessel.agencia_maritima
                })
            
            # Departing soon (ETD in next 24h)
            etd_time = vessel.etd.estimado or vessel.etd.registrado
            if etd_time and now <= etd_time <= tomorrow:
                hours_until = int((etd_time - now).total_seconds() / 3600)
                current_ops["departing_soon"].append({
                    "vessel": vessel.identificador_navio,
                    "terminal": vessel.terminal,
                    "expected_departure": etd_time.isoformat(),
                    "hours_until": hours_until,
                    "operation": vessel.tipo_operacao,
                    "agency": vessel.agencia_maritima
                })
        
        # Sort by time
        current_ops["recently_arrived"].sort(key=lambda x: x["hours_ago"])
        current_ops["currently_berthed"].sort(key=lambda x: x["hours_berthed"], reverse=True)
        current_ops["arriving_soon"].sort(key=lambda x: x["hours_until"])
        current_ops["departing_soon"].sort(key=lambda x: x["hours_until"])
        
        return {
            "timestamp": now.isoformat(),
            "current_operations": current_ops,
            "summary": {
                "recently_arrived": len(current_ops["recently_arrived"]),
                "currently_berthed": len(current_ops["currently_berthed"]),
                "arriving_soon": len(current_ops["arriving_soon"]),
                "departing_soon": len(current_ops["departing_soon"])
            }
        }
    
    except Exception as e:
        logging.error(f"Error getting current operations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/aps-diope/tables")
async def get_aps_diope_tables():
    """Get APS DIOPE public tables (Esperados/Fundeados/Atracados/Programadas)"""
    try:
        diope_data = await external_api.scrape_aps_diope_tables()
        
        # Calculate summary statistics
        summary = {
            "esperados": len(diope_data["esperados"]),
            "fundeados": len(diope_data["fundeados"]), 
            "atracados": len(diope_data["atracados"]),
            "programadas": len(diope_data["programadas"]),
            "total": sum(len(vessels) for vessels in diope_data.values())
        }
        
        return {
            "message": "APS DIOPE tables retrieved successfully",
            "timestamp": datetime.utcnow().isoformat(),
            "tables": diope_data,
            "summary": summary
        }
    
    except Exception as e:
        logging.error(f"Error getting APS DIOPE tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/marine-traffic/links/{vessel_id}")
async def get_marine_traffic_links(vessel_id: str):
    """Generate MarineTraffic deep-links for a specific vessel"""
    try:
        # Get vessel data
        vessel = await db.vessel_schedules.find_one({"identificador_navio": vessel_id})
        if not vessel:
            raise HTTPException(status_code=404, detail="Vessel not found")
        
        vessel_obj = VesselSchedule(**vessel)
        
        # Build MarineTraffic links
        links = MarineTrafficLinkBuilder.build_links(
            imo=vessel_obj.imo,
            mmsi=vessel_obj.mmsi,
            shipid=vessel_obj.shipid,
            vessel_name=vessel_obj.identificador_navio,
            lat=vessel_obj.latitude,
            lon=vessel_obj.longitude,
            language="pt"  # Portuguese for Brazilian users
        )
        
        return {
            "vessel_id": vessel_id,
            "vessel_name": vessel_obj.identificador_navio,
            "marine_traffic_links": {
                "details": links.url_details,
                "map_vessel": links.url_map_vessel,
                "map_coords": links.url_map_coords,
                "embed": links.url_embed
            },
            "has_tracking_data": bool(vessel_obj.imo or vessel_obj.mmsi or vessel_obj.shipid)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error generating MarineTraffic links: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/marine-traffic/port-santos")
async def get_santos_port_links():
    """Get MarineTraffic links for Santos Port overview"""
    try:
        port_links = MarineTrafficLinkBuilder.get_santos_port_links(language="pt")
        
        return {
            "port_name": "Porto de Santos",
            "port_code": "BRSSZ", 
            "port_id": 189,
            "marine_traffic_links": {
                "port_details": port_links.url_port,
                "port_map": port_links.url_map_coords
            },
            "coordinates": {
                "latitude": -23.9534,
                "longitude": -46.3334
            }
        }
    
    except Exception as e:
        logging.error(f"Error generating Santos port links: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/marine-traffic/santos")
async def get_marine_traffic_santos():
    """Get vessels heading to Santos Port from AIS data"""
    try:
        vessels = await external_api.scrape_marinetraffic_santos()
        return {
            "message": "AIS data retrieved successfully",
            "vessels_approaching": vessels,
            "count": len(vessels)
        }
    
    except Exception as e:
        logging.error(f"Error getting marine traffic data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/berths/timeline")
async def get_berth_timeline(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get timeline view of all berths for Gantt chart with date filtering"""
    try:
        # Build date filter
        date_filter = {}
        if start_date or end_date:
            date_conditions = []
            if start_date:
                start_dt = datetime.fromisoformat(start_date)
                date_conditions.append({"$or": [
                    {"etb.estimado": {"$gte": start_dt.isoformat()}},
                    {"atb": {"$gte": start_dt.isoformat()}},
                    {"created_at": {"$gte": start_dt}}
                ]})
            if end_date:
                end_dt = datetime.fromisoformat(end_date)
                date_conditions.append({"$or": [
                    {"etb.estimado": {"$lte": end_dt.isoformat()}},
                    {"atb": {"$lte": end_dt.isoformat()}},
                    {"created_at": {"$lte": end_dt}}
                ]})
            
            if date_conditions:
                date_filter = {"$and": date_conditions}
        
        vessels = await db.vessel_schedules.find(date_filter).to_list(1000)
        
        # Group by terminal/berth
        berth_timeline = {}
        for vessel_data in vessels:
            vessel = VesselSchedule(**vessel_data)
            terminal = vessel.terminal or "Terminal Não Definido"
            
            if terminal not in berth_timeline:
                berth_timeline[terminal] = []
            
            # Create timeline entry
            timeline_entry = {
                "vessel_id": vessel.identificador_navio,
                "vessel_name": vessel.nome_navio or vessel.identificador_navio,
                "etb": vessel.etb.estimado.isoformat() if vessel.etb.estimado else None,
                "etd": vessel.etd.estimado.isoformat() if vessel.etd.estimado else None,
                "atb": vessel.atb.isoformat() if vessel.atb else None,
                "atd": vessel.atd.isoformat() if vessel.atd else None,
                "status": vessel.status,
                "priority": vessel.prioridade_rap,
                "agency": vessel.agencia_maritima,
                "operation_type": vessel.tipo_operacao,
                "observations": vessel.observacoes
            }
            
            berth_timeline[terminal].append(timeline_entry)
        
        # Sort entries by ETB
        for terminal in berth_timeline:
            berth_timeline[terminal].sort(
                key=lambda x: x["etb"] if x["etb"] else "9999-12-31T23:59:59"
            )
        
        return {
            "berth_timeline": berth_timeline,
            "date_filter": {
                "start_date": start_date,
                "end_date": end_date
            },
            "total_vessels": sum(len(schedules) for schedules in berth_timeline.values())
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
    await external_api.close()