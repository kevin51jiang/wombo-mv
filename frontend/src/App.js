import logo from "./logo.svg";
import "./App.css";
import { Card } from "./Card";
import { styles } from "./Styles";

function App() {
  return (
    <div className="App">
      <div className="App-header">
        <h1>WomboMV</h1>
      </div>
      <br />
      <h2>Best MV Lol</h2>

      <div>Choose a style</div>

      <div>
        {styles.map((style) => (
          <Card {...style} />
        ))}
      </div>
    </div>
  );
}

export default App;
