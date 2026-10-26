"""Visible directional heads mirror SUMO while CARLA control actors remain intact."""
import carla, json, math

class SignalVisuals:

    def __init__(self, world, root, client=None):
        self.world = world
        self.client = client
        self.heads = []
        self.hidden = set()
        layout = json.loads((root / 'refined/scene/traffic_layout.json').read_text(encoding='utf-8'))
        library = world.get_blueprint_library()
        active_path = root / 'refined/ACTIVE.json'
        detailed = active_path.exists() and json.loads(active_path.read_text(encoding='utf-8')).get('visual_version') in ('visual-20260919-v1', 'visual-20260920-v2', 'visual-20260920-v3', 'visual-20260920-v4', 'visual-20260921-v5', 'visual-20260922-v6')
        prefix = 'static.prop.nanshadetailsignal_' if detailed else 'static.prop.nanshasignal_'
        for f in layout['fixtures']:
            (x, y, z) = f['point']
            (ux, uy) = f['u']
            tf = carla.Transform(carla.Location(x, -y, z), carla.Rotation(yaw=math.degrees(math.atan2(-uy, ux))))
            alternatives = {}
            for state in ('red', 'yellow', 'green'):
                bp = library.find(prefix + f['shape'] + '_' + state)
                alternatives[state] = bp
            self.heads.append(dict(fixture=f, tf=tf, blueprints=alternatives, actor=None, state=None))
        self.hidden = {o.id for o in world.get_environment_objects(carla.CityObjectLabel.Any) if o.name.startswith('BP_TLOpenDrive_RHT_C_')}
        world.enable_environment_objects(self.hidden, False)

    def update(self, states):
        changes = []
        for h in self.heads:
            f = h['fixture']
            values = {'green' if states[f['tls']][i] in 'Gg' else 'yellow' if states[f['tls']][i] in 'Yy' else 'red' for i in f['indices']}
            if len(values) != 1:
                raise RuntimeError('Incompatible phases share a visible signal head ' + str(f))
            state = next(iter(values))
            if state == h['state']:
                continue
            if self.client:
                changes.append((h, state))
                continue
            new = self.world.spawn_actor(h['blueprints'][state], h['tf'])
            new.set_simulate_physics(False)
            if h['actor'] is not None:
                h['actor'].destroy()
            h['actor'] = new
            h['state'] = state
        if changes:
            commands = []
            for (h, state) in changes:
                commands.append(carla.command.SpawnActor(h['blueprints'][state], h['tf']).then(carla.command.SetSimulatePhysics(carla.command.FutureActor, False)))
            replies = self.client.apply_batch_sync(commands, False)
            if any((r.has_error() for r in replies)):
                self.client.apply_batch([carla.command.DestroyActor(r.actor_id) for r in replies if not r.has_error()])
                raise RuntimeError('Signal visual batch failed: ' + str([r.error for r in replies if r.has_error()]))
            old = [carla.command.DestroyActor(h['actor']) for (h, _) in changes if h['actor'] is not None]
            if old:
                removed = self.client.apply_batch_sync(old, False)
                if any((r.has_error() for r in removed)):
                    raise RuntimeError('Could not remove previous signal visual')
            for ((h, state), r) in zip(changes, replies):
                h['actor'] = r.actor_id
                h['state'] = state

    def close(self):
        if self.client:
            self.client.apply_batch_sync([carla.command.DestroyActor(h['actor']) for h in self.heads if h['actor'] is not None], False)
            if self.hidden:
                self.world.enable_environment_objects(self.hidden, True)
            return
        for h in self.heads:
            if h['actor'] is not None:
                h['actor'].destroy()
        if self.hidden:
            self.world.enable_environment_objects(self.hidden, True)
