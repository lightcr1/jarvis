import { apiRequest } from "./client";

export type WeatherForecastDay = {
  date: string | null;
  high: number | null;
  low: number | null;
  rain_pct: number | null;
  condition: string;
};

export type WeatherResult = {
  city: string;
  country: string;
  temp: number | null;
  condition: string;
  code: number;
  wind_kmh: number | null;
  high: number | null;
  low: number | null;
  rain_pct: number | null;
  forecast: WeatherForecastDay[];
};

export function fetchWeather(city?: string) {
  const params = new URLSearchParams();
  if (city) params.set("city", city);
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<{ weather: WeatherResult }>(`/weather${query}`, { includeUser: true });
}
