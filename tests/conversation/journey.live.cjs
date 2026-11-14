// Keep the existing real-rehearsal entry point on the current one-click UI.
// Explicit opt-in authorizes two isolated simulated purchases.
if(process.env.RUN_JOURNEY_LIVE!=='1')process.exit(2);
process.env.RUN_GUIDED_JOURNEY_LIVE='1';
require('./journey.guided.live.cjs');
