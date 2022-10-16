import './App.css'

export const Card = (props) => {
  return (
    <div className="card" id={props.id}>
      <p><b>{props.name}</b></p>
      <hr />
      <img src={props.photo_url} />

      <p>Type: {props.model_type}</p>
    </div>
  );
};
