import com.lesfurets.jenkins.unit.BasePipelineTest
import org.junit.Before
import org.junit.Test

import static org.junit.Assert.assertTrue

class SayHelloTest extends BasePipelineTest {

    List<String> echoedLines = []

    @Before
    @Override
    void setUp() throws Exception {
        super.setUp()
        echoedLines = []
        // Jenkins가 없는 로컬 환경이라, 실제 echo step 대신 우리가 만든 mock으로 대체
        helper.registerAllowedMethod('echo', [String.class], { String msg -> echoedLines << msg })
    }

    @Test
    void 이름을_주면_이름을_포함한_인사가_출력된다() throws Exception {
        def sayHello = loadScript('vars/sayHello.groovy')
        sayHello.call('도연')

        assertTrue(echoedLines.any { it.contains('Hello, 도연') })
    }

    @Test
    void 이름이_없으면_기본값_World로_인사한다() throws Exception {
        def sayHello = loadScript('vars/sayHello.groovy')
        sayHello.call()

        assertTrue(echoedLines.any { it.contains('Hello, World') })
    }
}
