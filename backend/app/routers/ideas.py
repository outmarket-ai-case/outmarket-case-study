from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Idea
from app.schemas import IdeaCreate, IdeaOut

router = APIRouter(prefix="/api/ideas", tags=["ideas"])


@router.get("", response_model=list[IdeaOut])
async def list_ideas(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[Idea]:
    result = await session.execute(select(Idea).order_by(Idea.created_at.desc()).limit(limit))
    return list(result.scalars())


@router.post("", response_model=IdeaOut, status_code=status.HTTP_201_CREATED)
async def create_idea(
    payload: IdeaCreate,
    session: AsyncSession = Depends(get_session),
) -> Idea:
    idea = Idea(content=payload.content)
    session.add(idea)
    await session.commit()
    await session.refresh(idea)
    return idea
