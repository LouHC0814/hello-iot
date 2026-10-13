"""运行：解释器绝对路径 -m iot_demo；加 --live 可实时回放。"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .sensor import CHINA_TIME, collect, simulate, summarize, validate_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_start(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("时间格式示例：2026-10-13T09:00:00+08:00") from exc
    return parsed.replace(tzinfo=CHINA_TIME) if parsed.utcoffset() is None else parsed


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("请输入大于 0 的数字。") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("请输入大于 0 的有限数字。")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hello IoT 温湿度模拟演示（无须硬件）")
    parser.add_argument("--samples", type=int, default=120, help="样本数，默认 120")
    parser.add_argument("--interval", type=positive_float, default=30, help="模拟采样间隔（秒），默认 30")
    parser.add_argument("--seed", type=int, default=42, help="随机种子，默认 42")
    parser.add_argument("--start", type=parse_start, help="开始时间；省略时使用当前北京时间")
    parser.add_argument("--output", type=Path, default=Path("运行结果"), help="输出目录，默认 ./运行结果")
    parser.add_argument("--live", action="store_true", help="打开图形窗口，逐条回放模拟数据")
    parser.add_argument("--refresh", type=positive_float, default=0.3, help="实时回放每帧等待秒数，默认 0.3")
    return parser


def create_chart(live: bool):
    # 缓存留在项目里；在受限环境运行时无需向用户的配置目录写入。
    os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".runtime" / "matplotlib"))
    import matplotlib

    if not live:
        matplotlib.use("Agg")
    from matplotlib import font_manager
    from matplotlib import pyplot as plt
    from matplotlib.dates import AutoDateLocator, DateFormatter

    if live and matplotlib.get_backend().lower() in {"agg", "pdf", "svg", "ps", "pgf", "cairo", "template"}:
        raise RuntimeError("当前环境没有可用的图形窗口。请去掉 --live，直接生成曲线图片。")

    available = {font.name for font in font_manager.fontManager.ttflist}
    font = next((name for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei") if name in available), None)
    chinese = font is not None
    if font:
        plt.rcParams["font.sans-serif"] = [font, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.size"] = 10

    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    fig.patch.set_facecolor("#f4f7fb")
    fig.subplots_adjust(left=0.09, right=0.97, top=0.78, bottom=0.13, hspace=0.32)
    fig.text(0.09, 0.935, "HELLO IoT", color="#172b4d", fontsize=21, weight="bold")
    fig.text(0.09, 0.885, "温湿度采集演示 · 模拟数据" if chinese else "Temperature & humidity / SIMULATED DATA", color="#536780", fontsize=12)
    metrics = fig.text(0.09, 0.827, "", color="#172b4d", fontsize=11)
    colors = ("#de7145", "#168d9a")
    labels = ("温度 (°C)", "湿度 (%RH)") if chinese else ("Temperature (°C)", "Humidity (%RH)")
    lines = []
    for ax, color, label in zip(axes, colors, labels):
        ax.set_facecolor("white")
        ax.set_ylabel(label, color=color, fontsize=11)
        ax.grid(True, color="#e6edf5", linewidth=0.7)
        ax.tick_params(colors="#536780", labelsize=9)
        for spine in ax.spines.values():
            spine.set_visible(False)
        line, = ax.plot([], [], color=color, linewidth=2)
        lines.append(line)
    axes[1].set_xlabel("采样时间（见下方时区）" if chinese else "Sample time (timezone below)", color="#536780")
    footer = fig.text(0.09, 0.025, "", fontsize=9, color="#536780")

    def update(readings):
        timestamps = [item.timestamp for item in readings]
        values = ([item.temperature_c for item in readings], [item.humidity_pct for item in readings])
        for ax, line, series in zip(axes, lines, values):
            line.set_data(timestamps, series)
            line.set_marker("o" if len(readings) == 1 else "")
            ax.relim()
            ax.autoscale_view()
            ax.margins(y=0.25)
        if len(readings) == 1:
            axes[1].set_xlim(timestamps[0] - timedelta(seconds=30), timestamps[0] + timedelta(seconds=30))
        else:
            axes[1].set_xlim(timestamps[0], timestamps[-1])
        axes[1].xaxis.set_major_locator(AutoDateLocator(tz=timestamps[0].tzinfo, minticks=4, maxticks=8))
        axes[1].xaxis.set_major_formatter(DateFormatter("%H:%M:%S", tz=timestamps[0].tzinfo))
        latest = readings[-1]
        prefix = f"已采集 {len(readings)} 条" if chinese else f"{len(readings)} samples"
        metrics.set_text(f"{prefix}    |    {latest.temperature_c:.2f} °C    |    {latest.humidity_pct:.2f} %RH")
        date_range = f"{timestamps[0].isoformat()} — {timestamps[-1].isoformat()}"
        footer.set_text(date_range)
        if plt.fignum_exists(fig.number):
            fig.canvas.draw_idle()

    return plt, fig, update


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    start = args.start or datetime.now(CHINA_TIME).replace(microsecond=0)
    try:
        validate_settings(args.samples, args.interval, start)
    except ValueError as exc:
        parser.error(str(exc))

    plt = fig = None
    try:
        plt, fig, update = create_chart(args.live)
        args.output.mkdir(parents=True, exist_ok=True)
        csv_path = args.output / "温湿度记录.csv"
        if args.live:
            plt.ion()
            plt.show(block=False)

        def on_reading(readings):
            update(readings)
            plt.pause(args.refresh)

        readings, interrupted = collect(
            simulate(args.samples, args.interval, args.seed, start),
            csv_path,
            on_reading=on_reading if args.live else None,
            is_open=(lambda: plt.fignum_exists(fig.number)) if args.live else None,
        )
        if not readings:
            raise RuntimeError("窗口在采集开始前关闭；只保存了 CSV 表头。请重新运行。")
        update(readings)
        chart_path = args.output / "温湿度曲线.png"
        fig.savefig(chart_path, dpi=160, facecolor=fig.get_facecolor())
        summary = summarize(readings, args.samples, args.interval)
        summary_path = args.output / "统计摘要.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if interrupted and not summary["complete"]:
            print(f"采集提前结束，已保留 {len(readings)}/{args.samples} 条模拟记录。")
        else:
            print(f"已生成 {len(readings)} 条模拟记录（不是实测数据）。")
        print(f"温度均值：{summary['temperature_c']['mean']:.2f} °C；湿度均值：{summary['humidity_pct']['mean']:.2f} %RH")
        for path in (csv_path, chart_path, summary_path):
            print(path.resolve())
        return 0
    except (OSError, RuntimeError, ImportError) as exc:
        print(f"演示未完成：{exc}", file=sys.stderr)
        return 1
    finally:
        if plt is not None and fig is not None:
            plt.close(fig)
            if args.live:
                plt.ioff()


if __name__ == "__main__":
    raise SystemExit(main())
