// Check the in-browser stepper core (web/stepper.js) against known values / the C simulator.
// Run from busy-beaver/: node src/test_stepper.js
const { execFileSync } = require("child_process");
const path = require("path");
const Core = require(path.join(__dirname, "..", "web", "stepper.js"));
const cases = [
  "1RB1LB_1LA1RZ",                       // BB(2) = 6
  "1RB1RZ_1LB0RC_1LC1LA",                // BB(3) = 21
  "1RB1LB_1LA0LC_1RZ1LD_1RD0RA",         // BB(4) = 107
  "1RB2LA1RA1RA_1LB1LA3RB1RZ",           // BB(2,4) = 3,932,964
  "1RB1LC_1RC1RB_1RD0LE_1LA1LD_1RZ0LA",  // BB(5) = 47,176,870
  "1RB---_1LC0LF_1RC0RD_1LE1RD_1LB1RB_0RB1LF",
  "1RB---_1LB0RA",                       // stops on an undefined rule
];
let bad = 0;
for (const tm of cases) {
  const M = Core.machine(Core.parse(tm));
  const t = Date.now();
  while (M.status === "run" && M.steps < 50_000_000) Core.run(M, 1_000_000);
  const js = M.status === "run" ? `limit steps=${M.steps}` : `${M.status === "undef" ? "undefined" : "halt"} steps=${M.steps} nonzero=${M.nonzero} width=${M.hi - M.lo + 1}`;
  const c = execFileSync(path.join(__dirname, "..", "bb"), ["run", tm, "50000000"]).toString().trim();
  const ok = js === c || (js.startsWith("limit") && c.startsWith("limit"));
  if (!ok) bad++;
  console.log(ok ? "ok  " : "FAIL", tm, "| js:", js, "| c:", c, `| ${Date.now() - t} ms`);
}
process.exit(bad ? 1 : 0);
