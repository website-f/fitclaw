import base64
import binascii
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.device_command import DeviceCommand, DeviceCommandStatus

ARTIFACT_DIR = Path("/data/device_artifacts")


class DeviceControlService:
    @staticmethod
    def create_command(
        db: Session,
        agent_name: str,
        command_type: str,
        payload_json: dict | None = None,
        source: str = "api",
        created_by_user_id: str | None = None,
    ) -> DeviceCommand:
        command = DeviceCommand(
            agent_name=agent_name.strip(),
            command_type=command_type.strip(),
            payload_json=payload_json or {},
            source=source,
            created_by_user_id=created_by_user_id,
        )
        db.add(command)
        db.commit()
        db.refresh(command)
        return command

    @staticmethod
    def get_command(db: Session, command_id: str) -> DeviceCommand | None:
        return db.scalar(select(DeviceCommand).where(DeviceCommand.command_id == command_id))

    @staticmethod
    def list_commands(db: Session, agent_name: str | None = None, limit: int = 50) -> list[DeviceCommand]:
        stmt = select(DeviceCommand)
        if agent_name:
            stmt = stmt.where(DeviceCommand.agent_name == agent_name)
        stmt = stmt.order_by(DeviceCommand.created_at.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_latest_command(
        db: Session,
        agent_name: str,
        command_type: str | None = None,
        status: DeviceCommandStatus | None = None,
    ) -> DeviceCommand | None:
        stmt = select(DeviceCommand).where(DeviceCommand.agent_name == agent_name)
        if command_type:
            stmt = stmt.where(DeviceCommand.command_type == command_type)
        if status:
            stmt = stmt.where(DeviceCommand.status == status)
        stmt = stmt.order_by(DeviceCommand.created_at.desc()).limit(1)
        return db.scalar(stmt)

    @staticmethod
    def claim_next_command(db: Session, agent_name: str) -> DeviceCommand | None:
        candidates = list(
            db.scalars(
                select(DeviceCommand)
                .where(DeviceCommand.agent_name == agent_name)
                .where(DeviceCommand.status == DeviceCommandStatus.pending)
                .order_by(DeviceCommand.created_at.asc())
                .limit(10)
            ).all()
        )

        for candidate in candidates:
            result = db.execute(
                update(DeviceCommand)
                .where(DeviceCommand.id == candidate.id)
                .where(DeviceCommand.status == DeviceCommandStatus.pending)
                .values(status=DeviceCommandStatus.running, updated_at=utcnow())
            )
            if result.rowcount:
                db.commit()
                return DeviceControlService.get_command(db, candidate.command_id)

        db.rollback()
        return None

    @staticmethod
    def complete_command(
        db: Session,
        command_id: str,
        status: DeviceCommandStatus,
        result_json: dict | None = None,
        error_text: str | None = None,
    ) -> DeviceCommand | None:
        command = DeviceControlService.get_command(db, command_id)
        if command is None:
            return None

        payload = result_json or {}
        artifact_path = command.artifact_path
        if payload.get("artifact_base64"):
            artifact_path = str(DeviceControlService._write_artifact(command.agent_name, command.command_id, payload))
            payload = {key: value for key, value in payload.items() if key != "artifact_base64"}
            payload["artifact_saved"] = True

        command.status = status
        command.result_json = payload
        command.error_text = error_text
        command.artifact_path = artifact_path
        command.completed_at = utcnow()
        db.commit()
        db.refresh(command)
        return command

    @staticmethod
    def _write_artifact(agent_name: str, command_id: str, payload: dict) -> Path:
        raw_base64 = str(payload["artifact_base64"])
        extension = str(payload.get("artifact_ext", "bin")).lstrip(".") or "bin"
        agent_dir = ARTIFACT_DIR / agent_name
        agent_dir.mkdir(parents=True, exist_ok=True)
        output_path = agent_dir / f"{command_id}.{extension}"

        try:
            data = base64.b64decode(raw_base64)
        except binascii.Error as exc:
            raise ValueError(f"Invalid artifact base64 payload for command `{command_id}`.") from exc

        output_path.write_bytes(data)
        return output_path

