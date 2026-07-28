"""Deterministic time-series projection helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ForecastResult:
    forecast: pd.DataFrame
    chart_data: pd.DataFrame


def linear_monthly_forecast(
    data: pd.DataFrame,
    date_column: str,
    value_column: str,
    periods: int,
) -> ForecastResult:
    """Project a monthly series using its recent linear trend."""
    if date_column not in data.columns or value_column not in data.columns:
        raise ValueError("The projection query did not return the expected columns.")
    if not 1 <= periods <= 120:
        raise ValueError("Projection calculation exceeds the supported range.")

    history = data[[date_column, value_column]].copy()
    history.columns = ["period", "actual"]
    history["period"] = pd.to_datetime(history["period"], errors="coerce")
    history["actual"] = pd.to_numeric(history["actual"], errors="coerce")
    history = history.dropna().sort_values("period")
    history["period"] = history["period"].dt.to_period("M").dt.to_timestamp()
    history = history.groupby("period", as_index=False)["actual"].sum()

    if len(history) < 3:
        raise ValueError(
            "At least three months of historical data are needed for a projection."
        )

    complete_index = pd.date_range(
        history["period"].min(),
        history["period"].max(),
        freq="MS",
    )
    history = (
        history.set_index("period")
        .reindex(complete_index, fill_value=0)
        .rename_axis("period")
        .reset_index()
    )
    training = history.tail(24).reset_index(drop=True)
    x_values = [float(index) for index in range(len(training))]
    y_values = training["actual"].astype(float).tolist()
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    denominator = sum((value - x_mean) ** 2 for value in x_values)
    slope = (
        sum(
            (x_value - x_mean) * (y_value - y_mean)
            for x_value, y_value in zip(x_values, y_values)
        )
        / denominator
        if denominator
        else 0.0
    )
    intercept = y_mean - slope * x_mean

    future_rows = []
    for step in range(1, periods + 1):
        x_value = len(training) - 1 + step
        future_rows.append(
            {
                "period": history["period"].iloc[-1] + pd.DateOffset(months=step),
                "projected_value": round(max(0.0, intercept + slope * x_value)),
            }
        )
    forecast = pd.DataFrame(future_rows)
    forecast["projected_value"] = forecast["projected_value"].astype("int64")

    chart_data = history.copy()
    chart_data["projected"] = float("nan")
    chart_data.loc[chart_data.index[-1], "projected"] = chart_data["actual"].iloc[-1]
    future_chart = forecast.rename(columns={"projected_value": "projected"})
    future_chart["actual"] = float("nan")
    chart_data = pd.concat(
        [chart_data, future_chart[["period", "actual", "projected"]]],
        ignore_index=True,
    )
    return ForecastResult(forecast=forecast, chart_data=chart_data)


def grouped_monthly_forecast(
    data: pd.DataFrame,
    date_column: str,
    series_column: str,
    value_column: str,
    periods: int,
) -> ForecastResult:
    """Project multiple monthly series independently over a shared date range."""
    required = {date_column, series_column, value_column}
    if not required.issubset(data.columns):
        raise ValueError(
            "The grouped projection query did not return the expected columns."
        )

    history = data[[date_column, series_column, value_column]].copy()
    history.columns = ["period", "series", "value"]
    history["period"] = pd.to_datetime(history["period"], errors="coerce")
    history["value"] = pd.to_numeric(history["value"], errors="coerce")
    history["series"] = history["series"].fillna("Unknown").astype(str)
    history = history.dropna(subset=["period", "value"])
    history["period"] = history["period"].dt.to_period("M").dt.to_timestamp()
    history = history.groupby(
        ["series", "period"],
        as_index=False,
    )["value"].sum()
    if history.empty:
        raise ValueError("No valid historical data was returned for projection.")

    complete_index = pd.date_range(
        history["period"].min(),
        history["period"].max(),
        freq="MS",
    )
    forecasts = []
    charts = []
    for series, series_history in history.groupby("series", sort=True):
        complete_history = (
            series_history.set_index("period")[["value"]]
            .reindex(complete_index, fill_value=0)
            .rename_axis("period")
            .reset_index()
        )
        result = linear_monthly_forecast(
            complete_history,
            date_column="period",
            value_column="value",
            periods=periods,
        )
        series_forecast = result.forecast.copy()
        series_forecast.insert(0, "series", series)
        forecasts.append(series_forecast)

        series_chart = result.chart_data.copy()
        series_chart.insert(0, "series", series)
        charts.append(series_chart)

    return ForecastResult(
        forecast=pd.concat(forecasts, ignore_index=True),
        chart_data=pd.concat(charts, ignore_index=True),
    )
