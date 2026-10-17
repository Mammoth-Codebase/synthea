package org.mitre.synthea.export;

import static org.junit.Assert.assertEquals;

import org.junit.Test;
import org.mitre.synthea.world.agents.Person;
import org.mitre.synthea.world.concepts.HealthRecord.Observation;

public class ExportHelperTest {

  @Test
  public void numericObservationValuesOfAnyNumberType() {
    Person person = new Person(0L);
    Observation integerValued = person.record.new Observation(0L, "cd4", Integer.valueOf(512));
    assertEquals("numeric", ExportHelper.getObservationType(integerValued));
    assertEquals("512.0", ExportHelper.getObservationValue(integerValued));

    Observation doubleValued = person.record.new Observation(0L, "temp", Double.valueOf(37.25));
    assertEquals("numeric", ExportHelper.getObservationType(doubleValued));
    assertEquals("37.3", ExportHelper.getObservationValue(doubleValued));

    Observation longValued = person.record.new Observation(0L, "viral load", Long.valueOf(40L));
    assertEquals("numeric", ExportHelper.getObservationType(longValued));
    assertEquals("40.0", ExportHelper.getObservationValue(longValued));
  }

  @Test
  public void textObservationValues() {
    Person person = new Person(0L);
    Observation text = person.record.new Observation(0L, "note", "negative");
    assertEquals("text", ExportHelper.getObservationType(text));
    assertEquals("negative", ExportHelper.getObservationValue(text));
  }
}
