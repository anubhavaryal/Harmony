import { useEffect, useState } from "react";
// import logo from "./logo.svg";
import "./App.css";
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
  const [progress, setProgress] = useState(-1);
  const [stage, setStage] = useState(-1);

  useEffect(() => {
    const interval = setInterval(() => {
      axios
        .get("/api/channel/979554513021177909/pog")
        .then((res) => setProgress(res.data.progress));
    }, 250);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      axios
        .get("/api/channel/979554513021177909/stage")
        .then((res) => setStage(res.data.stage));
    }, 250);

    return () => clearInterval(interval);
  }, []);

  let startAnalysis = () => {
    console.log("starting analysis");
    axios.put("/api/channel/979554513021177909/start");
  };

  let stopAnalysis = () => {
    console.log("stopping analysis");
    axios.put("/api/channel/979554513021177909/stop");
  };

  let setLimit = () => {
    console.log("setting limit");
    axios.put("/api/channel/979554513021177909/limit", { limit: 50 });
  };

  return (
    <div>
      <p>stage: {stage}</p>
      <p>progress: {progress}</p>
      <button onClick={startAnalysis}>click me to start analysis</button>
      <button onClick={stopAnalysis}>click me to stop analysis</button>
      <button onClick={setLimit}>click me to set limit</button>
    </div>
  );
  // const [count, setCount] = useState(0);

  // return (
  //   <div className="App">
  //     <header className="App-header">
  //       <img src={logo} className="App-logo" alt="logo" />
  //       <p>Hello Vite + React!</p>
  //       <p>
  //         <button type="button" onClick={() => setCount((count) => count + 1)}>
  //           count is: {count}
  //         </button>
  //       </p>
  //       <p>
  //         Edit <code>App.jsx</code> and save to test HMR updates.
  //       </p>
  //       <p>
  //         <a
  //           className="App-link"
  //           href="https://reactjs.org"
  //           target="_blank"
  //           rel="noopener noreferrer"
  //         >
  //           Learn React
  //         </a>
  //         {" | "}
  //         <a
  //           className="App-link"
  //           href="https://vitejs.dev/guide/features.html"
  //           target="_blank"
  //           rel="noopener noreferrer"
  //         >
  //           Vite Docs
  //         </a>
  //       </p>
  //     </header>
  //   </div>
  // );
}

export default App;
