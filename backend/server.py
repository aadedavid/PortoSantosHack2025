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


@api_router.get("/berths/timeline")
async def get_berth_timeline():
    """Get timeline view of all berths for Gantt chart"""
    try:
        vessels = await db.vessel_schedules.find().to_list(1000)
        
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
        
        return berth_timeline
    
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