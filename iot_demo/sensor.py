"""模拟传感器与记录导出；这一层只用 Python 标准库。"""

import csv
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator

CHINA_TIME = timezone(timedelta(hours=8))
CSV_FIELDS = ("timestamp", "temperature_c", "humidity_pct", "source")


@dataclass(frozen=True)
class Reading:
    timestamp: datetime
    temperature_c: float
    humidity_pct: float
    source: str = "simulated"

    def as_row(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "temperature_c": self.temperature_c,
            "humidity_pct": self.humidity_pct,
            "source": self.source,
        }


def validate_settings(samples: int, interval: float, start: datetime) -> None:
    if samples < 1:
        raise ValueError("样本数必须至少为 1。")
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError("模拟采样间隔必须是大于 0 的有限数字。")
    if start.utcoffset() is None:
        raise ValueError("开始时间必须包含时区。")
    try:
        start + timedelta(seconds=(samples - 1) * interval)
    except (OverflowError, ValueError) as exc:
        raise ValueError("样本数与采样间隔过大，时间超出可表示范围。") from exc


def simulate(
    samples: int, interval: float, seed: int, start: datetime
) -> Iterator[Reading]:
    """正弦趋势叠加小幅噪声；同样的参数会生成同样的数据。"""
    validate_settings(samples, interval, start)
    rng = random.Random(seed)
    for index in range(samples):
        elapsed = index * interval
        # 每两小时完成一个变化周期；这是演示模型，不是天气预测。
        phase = 2 * math.pi * (elapsed % 7200) / 7200
        temperature = 25 + 2.2 * math.sin(phase) + rng.gauss(0, 0.15)
        humidity = 60 - 6 * math.sin(phase) + rng.gauss(0, 0.5)
        yield Reading(
            timestamp=start + timedelta(seconds=elapsed),
            temperature_c=round(max(10, min(40, temperature)), 2),
            humidity_pct=round(max(20, min(95, humidity)), 2),
        )


def collect(
    source: Iterable[Reading],
    csv_path: Path,
    on_reading: Callable[[list[Reading]], None] | None = None,
    is_open: Callable[[], bool] | None = None,
) -> tuple[list[Reading], bool]:
    """逐条写入 CSV。窗口关闭或 Ctrl+C 时保留已经采集的记录。"""
    readings = []
    interrupted = False
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        stream.flush()
        try:
            for reading in source:
                if is_open is not None and not is_open():
                    interrupted = True
                    break
                writer.writerow(reading.as_row())
                stream.flush()
                readings.append(reading)
                if on_reading is not None:
                    on_reading(readings)
        except KeyboardInterrupt:
            interrupted = True
    return readings, interrupted


def summarize(readings: list[Reading], requested: int, interval: float) -> dict:
    if not readings:
        raise ValueError("还没有采集到数据，无法生成统计摘要。")

    def statistics(values: list[float]) -> dict:
        return {
            "min": min(values),
            "max": max(values),
            "mean": round(sum(values) / len(values), 2),
            "latest": values[-1],
        }

    return {
        "source": "simulated",
        "说明": "数据由程序模拟生成，不来自真实传感器。",
        "requested_samples": requested,
        "collected_samples": len(readings),
        "complete": len(readings) == requested,
        "simulated_interval_seconds": interval,
        "start": readings[0].timestamp.isoformat(),
        "end": readings[-1].timestamp.isoformat(),
        "temperature_c": statistics([item.temperature_c for item in readings]),
        "humidity_pct": statistics([item.humidity_pct for item in readings]),
    }
