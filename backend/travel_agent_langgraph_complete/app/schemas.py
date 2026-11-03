from typing import Literal, Optional, List
from pydantic import BaseModel, Field

class IntentResult(BaseModel):
    is_travel: bool
    confidence: float = Field(ge=0, le=1)
    reason: str

class TravelPreferences(BaseModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None
    return_date: Optional[str] = None
    travelers: Optional[int] = None
    budget_total_inr: Optional[float] = None
    travel_modes: List[str] = Field(default_factory=list)
    train_class: Optional[str] = None
    flight_cabin: Optional[str] = None
    departure_time_preference: Optional[str] = None
    arrival_time_preference: Optional[str] = None
    hotel_required: Optional[bool] = None
    hotel_budget_per_night_inr: Optional[float] = None
    hotel_area_preference: Optional[str] = None
    special_requirements: List[str] = Field(default_factory=list)

class RequirementResult(BaseModel):
    preferences: TravelPreferences
    missing_required_fields: List[str]
    questions: List[str]
    ready_for_research: bool

class LocationCandidate(BaseModel):
    name: str
    code: Optional[str] = None
    type: str

class LocationResolution(BaseModel):
    origin_candidates: List[LocationCandidate] = Field(default_factory=list)
    destination_candidates: List[LocationCandidate] = Field(default_factory=list)
    needs_user_choice: bool = False
    explanation: str

class ResearchPlan(BaseModel):
    search_trains: bool
    search_flights: bool
    search_hotels: bool
    rationale: str

class TravelOption(BaseModel):
    option_id: str
    category: Literal["train", "flight", "hotel"]
    title: str
    provider: str
    departure: Optional[str] = None
    arrival: Optional[str] = None
    duration: Optional[str] = None
    price_inr: Optional[float] = None
    refundable: Optional[bool] = None
    details: List[str] = Field(default_factory=list)
    fit_score: float = Field(ge=0, le=100)

class Recommendations(BaseModel):
    trains: List[TravelOption] = Field(default_factory=list)
    flights: List[TravelOption] = Field(default_factory=list)
    hotels: List[TravelOption] = Field(default_factory=list)

class Selection(BaseModel):
    approved_option_ids: List[str] = Field(default_factory=list)
    user_message: str

class PaymentApproval(BaseModel):
    approved: bool
    confirmation_text: str

class BookingResult(BaseModel):
    status: Literal["booked", "rejected", "awaiting_payment", "error"]
    message: str
    booking_reference: Optional[str] = None
