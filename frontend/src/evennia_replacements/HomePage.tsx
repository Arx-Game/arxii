import { Link } from 'react-router-dom'
import { useHomeStats } from './queries'

export function HomePage() {
  const { data } = useHomeStats()

  return (
    <div className="container mx-auto mt-4" id="main-copy">
      <div className="row">
        <div className="col">
          <div className="card text-center">
            <div className="card-body">
              <h1 className="card-title">Welcome to Arx II!</h1>
              <hr />
              <p className="lead">The Python MUD/MU* creation system.</p>
              <p>
                You are looking at the start of your game's website, generated out of the box by
                Evennia.
                <br />
                It can be expanded into a full-fledged home for your game.
              </p>
              <p>
                <Link to="/game" className="playbutton">
                  Play in the browser!
                </Link>
              </p>
            </div>
          </div>
        </div>
      </div>
      {data && (
        <div className="row mt-4">
          <div className="col-12 col-md-4 mb-3">
            <div className="card">
              <h4 className="card-header text-center">Accounts</h4>
              <div className="card-body">
                <p>
                  There's currently <strong>{data.num_accounts_connected}</strong> connected out of
                  a total of <strong>{data.num_accounts_registered}</strong> account
                  {data.num_accounts_registered !== 1 && 's'} registered.
                </p>
                <p>
                  Of these, <strong>{data.num_accounts_registered_recent}</strong> were created this
                  week, and <strong>{data.num_accounts_connected_recent}</strong> have connected
                  within the last seven days.
                </p>
              </div>
            </div>
          </div>
          <div className="col-12 col-md-4 mb-3">
            <div className="card">
              <h4 className="card-header text-center">Recently Connected</h4>
              <div className="card-body px-0 py-0">
                <ul className="list-group">
                  {data.accounts_connected_recent.map((a) => (
                    <li key={a.username} className="list-group-item">
                      {a.username}&mdash;<em>{a.last_login} ago</em>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
          <div className="col-12 col-md-4 mb-3">
            <div className="card">
              <h4 className="card-header text-center">Database Stats</h4>
              <div className="card-body py-0 px-0">
                <ul className="list-group">
                  <li className="list-group-item">
                    {data.num_accounts_registered} account
                    {data.num_accounts_registered !== 1 && 's'} (+ {data.num_characters} character
                    {data.num_characters !== 1 && 's'})
                  </li>
                  <li className="list-group-item">
                    {data.num_rooms} room{data.num_rooms !== 1 && 's'} (+ {data.num_exits} exits)
                  </li>
                  <li className="list-group-item">{data.num_others} other objects</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
