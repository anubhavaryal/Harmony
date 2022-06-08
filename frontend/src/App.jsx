import { useEffect, useState } from "react";
import axios from "axios";

axios.defaults.baseURL = "http://localhost:5000";
/**
 * app will first call /start which starts analysis
 * app will keep requesting /pog for progress and display that progress to user
 * once /pog shows analysis is complete the user can request their data through /sentiment endpoints
 * analysis can be stopped at any time with /stop
 * maybe backend will require frequent pings with /ping or smth so it knows to continue analysis because if frontend loses connections thats a big rip
 */

function App() {
  return <h1 className="text-4xl text-red-500">Harmony</h1>;
}

export default App;
