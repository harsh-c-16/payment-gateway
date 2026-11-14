"use strict";
(() => {
  let busy=false,paused=false,timer=null,last=null;
  const label=document.getElementById("boundary-status");
  async function refresh(manual=false) {
    clearTimeout(timer);if(busy || (paused && !manual))return;busy=true;
    try {
      const response=await fetch("http://127.0.0.1:8010/journey/snapshot",{cache:"no-store",credentials:"omit",signal:AbortSignal.timeout(40000)});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      last=await response.json();window.JourneyView.boundaries(last);
      label.textContent=`Observed ${window.JourneyView.stamp(last.observed_at)} · ${last.namespace} · independent read-only diagnostic harness. ${last.unavailable.length ? "Unavailable: "+last.unavailable.join(", ") : ""}`;
    }catch(e){label.textContent=`${last ? "Displayed observations are stale. " : "Observations unavailable. "}Start start-failure-demo.ps1. ${e.message}`;}
    finally{busy=false;if(!paused && !document.hidden)timer=setTimeout(refresh,5000);}
  }
  window.addEventListener("observation-pause",e=>{paused=e.detail.paused;clearTimeout(timer);if(!paused)refresh();});
  window.addEventListener("observation-refresh",()=>refresh(true));
  document.addEventListener("visibilitychange",()=>{clearTimeout(timer);if(!document.hidden && !paused)refresh();});
  refresh();
})();
