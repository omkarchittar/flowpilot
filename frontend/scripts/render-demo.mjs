import { spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

const [input, output = "../docs/demo.gif"] = process.argv.slice(2);
if (!input || resolve(input) === resolve(output)) {
  throw new Error(
    "Usage: node scripts/render-demo.mjs INPUT.webm [OUTPUT.gif]",
  );
}
mkdirSync(dirname(resolve(output)), { recursive: true });
const result = spawnSync(
  process.env.FFMPEG_BIN || "ffmpeg",
  [
    "-hide_banner",
    "-loglevel",
    "warning",
    "-y",
    "-i",
    resolve(input),
    "-filter_complex",
    "fps=8,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3",
    "-loop",
    "0",
    resolve(output),
  ],
  { stdio: "inherit" },
);
if (result.error) throw result.error;
if (result.status !== 0)
  throw new Error(`FFmpeg exited with ${result.status ?? result.signal}`);
console.log(`Recorded demo encoded: ${resolve(output)}`);
