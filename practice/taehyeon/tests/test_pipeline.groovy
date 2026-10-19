import groovy.json.JsonOutput
import groovy.json.JsonSlurperClassic
import org.codehaus.groovy.control.CompilerConfiguration

// Evaluate the actual Jenkinsfile. Only Jenkins/SSH/shell boundaries are replaced.
// This does not emulate CPS, real parallel cancellation or Jenkins plugin validation.
abstract class PipelineFixture extends Script {
    Map env = [BUILD_NUMBER:'42', WORKSPACE:'/workspace']
    Map params = [ACTION:'DEPLOY', OBSERVE_SECONDS:'1', MIN_SAMPLES:'1', MAX_RESPONSE_MS:'2000']
    Map scm = [:]
    Map files = [:]
    List events = []
    Map building
    Closure rootStages
    Map rootPost = [:]
    Map registeringPost
    Throwable failure
    boolean unfinished = false
    boolean failAfterCommit = false
    boolean committed = false
    String pendingOwner
    final String report = 'practice/taehyeon/.canary/reports'
    final String imageId = 'sha256:' + '1' * 64

    Object getProperty(String name) {
        if(this.@env != null && this.@env.containsKey(name)) return this.@env[name]
        super.getProperty(name)
    }
    def invokeBody(Closure c) { c.delegate=this; c.resolveStrategy=Closure.DELEGATE_FIRST; c() }
    def pipeline(Closure c) {
        invokeBody(c)
        try { invokeBody(rootStages) } catch (Throwable error) { failure=error }
        try {
            if (failure && rootPost.unsuccessful) invokeBody(rootPost.unsuccessful)
            if (rootPost.always) invokeBody(rootPost.always)
        } finally { if(rootPost.cleanup) invokeBody(rootPost.cleanup) }
    }
    def stage(String name, Closure c) {
        def parent=building
        def spec=[name:name, allowed:true, post:[:]]
        building=spec; invokeBody(c); building=parent
        if (!spec.allowed) return
        events << 'stage:'+name
        try { if(spec.body) invokeBody(spec.body) }
        finally { if(spec.post.always) invokeBody(spec.post.always) }
    }
    def stages(Closure c) { if(building != null) building.body=c; else rootStages=c }
    def steps(Closure c) { building.body=c }
    def parallel(Closure c) { building.body=c }
    def when(Closure c) { invokeBody(c) }
    def expression(Closure c) { building.allowed=(boolean)c() }
    def post(Closure c) { registeringPost=building == null ? rootPost : building.post; invokeBody(c); registeringPost=null }
    def always(Closure c) { registeringPost.always=c }
    def unsuccessful(Closure c) { registeringPost.unsuccessful=c }
    def cleanup(Closure c) { registeringPost.cleanup=c }
    def environment(Closure c) { c.delegate=env; c.resolveStrategy=Closure.DELEGATE_FIRST; c() }
    def parameters(Closure c) { invokeBody(c) }
    def string(Map m) { if(!params.containsKey(m.name)) params[m.name]=m.defaultValue }
    def choice(Map m) { if(!params.containsKey(m.name)) params[m.name]=m.choices[0] }
    def agent(Closure c) {}
    def options(Closure c) {}
    def failFast(boolean value) {}
    def checkout(Object value) { events << 'checkout' }
    def script(Closure c) { invokeBody(c) }
    def dir(String path, Closure c) { invokeBody(c) }
    def sshagent(Map m, Closure c) { invokeBody(c) }
    def timeout(Map m, Closure c) { invokeBody(c) }
    def waitUntil(Map m, Closure c) { assert c() }
    def withEnv(List values, Closure c) {
        def old=[:]
        values.each { def pair=it.toString().split('=',2); old[pair[0]]=env[pair[0]]; env[pair[0]]=pair[1] }
        try { invokeBody(c) } finally { old.each { k,v -> if(v==null) env.remove(k); else env[k]=v } }
    }
    def pwd() { env.WORKSPACE }
    def echo(String value) { events << 'echo:'+value }
    def error(String value) { throw new IllegalStateException(value) }
    def fileExists(String path) { files.containsKey(path) || path.endsWith('monitor.ready') }
    def writeFile(Map m) { files[m.file.toString()]=m.text.toString() }
    def readFile(String path) { assert files.containsKey(path):'Missing fixture file '+path; files[path] }
    def archiveArtifacts(Map m) { events << 'artifacts' }
    def jsonFile(String name, Object value) { files[report+'/'+name]=JsonOutput.toJson(value) }
    Map plan() {
        [before_state:[active_slot:'a',metadata:[version:'41',gitSha:'oldsha',release:'build-41-oldsha'],release_id:'build-41-oldsha'],
         target_state:[active_slot:'b',metadata:[version:'42',gitSha:'newsha',release:'build-42-newsha'],release_id:'build-42-newsha']]
    }
    def sh(Object argument) {
        String command=argument instanceof Map ? argument.script : argument.toString()
        if(command.contains('git rev-parse')) return 'abcdef0123456789abcdef0123456789abcdef01\n'
        if(command.contains('docker image inspect')) return imageId+'\n'
        if(command.contains('rm -rf')) events << 'clear-report'
        if(command.contains('gradle-in-docker.sh')) events << 'gradle'
        if(command.contains('docker build')) events << 'docker-build'
        if(command.contains('ansible-playbook') && env.CANARY_PLAYBOOK) {
            def vars=new JsonSlurperClassic().parseText(files[report+'/step-vars.json'])
            String play=env.CANARY_PLAYBOOK
            events << 'ansible:'+play+':'+(vars.operation_phase ?: vars.archive_source ?: '')
            switch(play) {
                case 'canary-state': jsonFile('previous-state.json',plan().before_state); break
                case 'release-archive':
                    jsonFile('archived-release.json',[image:[id:imageId,archive_sha256:'2'*64]])
                    if(vars.archive_source=='active') jsonFile('previous-state.json',plan().before_state)
                    break
                case 'deployment-plan': jsonFile('deployment-plan.json',plan()); break
                case 'rollback-prepare':
                    jsonFile('rollback-plan.json',plan())
                    jsonFile('rollback-vars.json',[nginx_backends:[],deployment_state:plan().target_state]); break
                case 'release-operation':
                    if(vars.operation_phase=='read') jsonFile('operation-status.json', [pending:unfinished,operation_id:pendingOwner ?: 'older-build'])
                    if(vars.operation_phase=='begin') { unfinished=true; pendingOwner=env.OPERATION_ID }
                    if(vars.operation_phase=='finalize') {
                        committed=true
                        unfinished=failAfterCommit
                        if(failAfterCommit) throw new IllegalStateException('Injected failure after durable commit')
                    }
                    if(vars.operation_phase=='recover') {
                        unfinished=false
                        jsonFile('operation-status.json',[pending:false,resolution:committed ? 'finalized' : 'recovered'])
                    }
                    break
                case 'canary-recover': files.remove(report+'/recovery-needed.json'); break
            }
        }
        return argument instanceof Map && argument.returnStdout ? '' : 0
    }
}

def configuration=new CompilerConfiguration(scriptBaseClass:PipelineFixture.name)
def source=new File(args ? args[0] : 'practice/taehyeon/Jenkinsfile')
def create={ Map overrides=[:] ->
    def pipeline=new GroovyShell(PipelineFixture.class.classLoader,new Binding(),configuration).parse(source)
    overrides.each { k,v -> pipeline."$k"=v }
    pipeline
}
def cases=[
    rollbackSkipsBuildAndCurrentBaseline:{
        def p=create(); p.params.ACTION='ROLLBACK'; p.run()
        assert p.failure==null: p.failure
        assert !p.events.contains('gradle') && !p.events.contains('docker-build')
        assert !p.events.any{it.startsWith('ansible:canary-state:')}
        assert p.events.contains('ansible:rollback-prepare:prepare')
        assert p.events.contains('ansible:release-operation:finalize')
        assert !p.env.RELEASE_ID
    },
    deployArchivesBeforeFirstSlotMutation:{
        def p=create(); p.run(); assert p.failure==null:p.failure
        int archive=p.events.indexOf('ansible:release-archive:candidate')
        int begin=p.events.indexOf('ansible:release-operation:begin')
        int mutate=p.events.indexOf('ansible:canary-app:')
        assert archive>=0 && begin>archive && mutate>begin
        assert p.events.contains('ansible:release-operation:finalize')
    },
    pendingRecoveryStopsNewOperation:{
        def p=create(unfinished:true); p.run(); assert p.failure==null:p.failure
        assert p.events.contains('ansible:release-operation:recover')
        assert !p.events.contains('gradle') && !p.events.contains('ansible:release-operation:begin')
    },
    committedFailureDoesNotUndoPromotion:{
        def p=create(failAfterCommit:true); p.run()
        assert p.failure!=null
        assert p.events.count('ansible:release-operation:recover')==1
        assert !p.events.any{it.startsWith('ansible:canary-recover:')}
    },
    previousStateDoesNotOverwriteCandidateMetadata:{
        def p=create(); p.run(); assert p.failure==null:p.failure
        assert p.files.containsKey(p.report+'/baseline-vars.json')
        def baseline=new JsonSlurperClassic().parseText(p.files[p.report+'/baseline-vars.json'])
        assert baseline.keySet()==['active_slot','metadata'] as Set
        assert baseline.metadata.release=='build-41-oldsha'
        def deployment=new JsonSlurperClassic().parseText(p.files[p.report+'/deployment-vars.json'])
        assert deployment.release_id.startsWith('build-42-')
    },
    legacyMarkerIsNotErased:{
        def p=create(); p.files[p.report+'/recovery-needed.json']='{}'; p.run()
        assert p.failure==null:p.failure
        assert p.events.contains('ansible:canary-recover:')
        assert !p.events.contains('clear-report') && !p.events.contains('gradle')
    }
]
int failures=0
cases.each { name,test ->
    try { test(); println 'PASS '+name } catch(Throwable error) { failures++; println 'FAIL '+name+': '+error }
}
assert failures==0: failures+' pipeline tests failed'
