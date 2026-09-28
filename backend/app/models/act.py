from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Act(Base):
    __tablename__ = "acts"
    __table_args__ = (
        UniqueConstraint("show_id", "band_id", name="uq_act"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id"), index=True)
    band_id: Mapped[int] = mapped_column(ForeignKey("bands.id"), index=True)
    position: Mapped[int] = mapped_column(default=0)  # 0 = headliner

    show: Mapped["Show"] = relationship(back_populates="acts")
    band: Mapped["Band"] = relationship(back_populates="acts")
