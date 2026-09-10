"""Contexto de la aplicacion: arma y comparte las dependencias.

Un solo lugar donde se construyen la conexion, los repositorios y los
servicios. Las pantallas reciben este objeto en lugar de abrir conexiones por
su cuenta, que es lo que hacia cada ventana de la version anterior.
"""

from __future__ import annotations

from app.config import AppConfig
from app.db.connection import Database
from app.db.migrations import migrate
from app.db.repositories import (
    AuditRepository,
    CatalogRepository,
    FatigueRepository,
    GenericRepository,
    MaintenanceRepository,
    RotaryRepository,
    WorkOrderRepository,
)
from app.models import QUASI, TORSION
from app.services.catalogs import CatalogService


class AppContext:
    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig.load()
        self.database = Database(self.config.database)

        self.audit = AuditRepository(self.database)
        self.catalog_repository = CatalogRepository(self.database)
        self.catalogs = CatalogService(self.catalog_repository)

        self.fatigue = FatigueRepository(self.database, self.audit)
        self.rotary = RotaryRepository(self.database, self.audit)
        self.torsion = GenericRepository(self.database, self.audit, TORSION.table)
        self.quasi = GenericRepository(self.database, self.audit, QUASI.table)
        self.work_orders = WorkOrderRepository(self.database, self.audit)
        self.maintenance = MaintenanceRepository(self.database, self.audit)

    def prepare(self) -> list[str]:
        """Aplica migraciones pendientes y carga los catalogos."""
        applied = migrate(self.database)
        self.catalogs.load()
        return applied

    def generic_repository(self, key: str) -> GenericRepository:
        return {"torsion": self.torsion, "quasi": self.quasi}[key]

    def reload_database(self, path: str) -> None:
        """Reapunta la app a otra base sin reiniciar (cambio desde Ajustes)."""
        self.config.database_path = path
        self.config.save()

        self.database = Database(self.config.database)
        self.audit = AuditRepository(self.database)
        self.catalog_repository = CatalogRepository(self.database)
        self.catalogs.repository = self.catalog_repository

        self.fatigue = FatigueRepository(self.database, self.audit)
        self.rotary = RotaryRepository(self.database, self.audit)
        self.torsion = GenericRepository(self.database, self.audit, TORSION.table)
        self.quasi = GenericRepository(self.database, self.audit, QUASI.table)
        self.work_orders = WorkOrderRepository(self.database, self.audit)
        self.maintenance = MaintenanceRepository(self.database, self.audit)

        self.prepare()
        self.catalogs.reload()
