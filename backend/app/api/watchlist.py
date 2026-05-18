"""Watchlist API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistResponse(BaseModel):
    tickers: list[str]


class AddTickerRequest(BaseModel):
    ticker: str


class TickerResponse(BaseModel):
    ticker: str


def _normalize(raw: object) -> str:
    """Validate and normalize a ticker symbol. Raises 400 on bad input."""
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="Ticker must be a string")
    normalized = raw.strip().upper()
    if not normalized:
        raise HTTPException(status_code=400, detail="Ticker must not be empty")
    if not normalized.isalnum():
        raise HTTPException(status_code=400, detail="Ticker must be alphanumeric")
    return normalized


@router.get("", response_model=WatchlistResponse)
async def get_watchlist(request: Request) -> WatchlistResponse:
    """Return the current watchlist tickers (alphabetical)."""
    repo = request.app.state.repo
    return WatchlistResponse(tickers=repo.list_tickers())


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TickerResponse)
async def add_ticker(payload: AddTickerRequest, request: Request) -> TickerResponse:
    """Add a ticker to the watchlist."""
    ticker = _normalize(payload.ticker)
    repo = request.app.state.repo
    source = request.app.state.source

    if not repo.add(ticker):
        raise HTTPException(status_code=400, detail=f"{ticker} is already on the watchlist")

    # Start streaming prices for the new ticker.
    await source.add_ticker(ticker)
    return TickerResponse(ticker=ticker)


@router.delete("/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_ticker(ticker: str, request: Request) -> Response:
    """Remove a ticker from the watchlist."""
    normalized = _normalize(ticker)
    repo = request.app.state.repo
    source = request.app.state.source

    if not repo.remove(normalized):
        raise HTTPException(status_code=404, detail=f"{normalized} not found on watchlist")

    await source.remove_ticker(normalized)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
